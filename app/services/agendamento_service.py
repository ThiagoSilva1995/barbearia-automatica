# app/services/agendamento_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from sqlalchemy.orm import selectinload
from datetime import date, time, datetime, timedelta
from typing import List, Optional, Dict
from decimal import Decimal

from app.models.agendamento import Agendamento
from app.models.servico import Servico, agendamento_servico
from app.models.produto import Produto, agendamento_produto
from app.schemas.agendamento import AgendamentoCreate

# =============================================================================
# FUNÇÕES AUXILIARES INTERNAS (LÓGICA LEVE)
# =============================================================================


async def _get_duracao_total(db: AsyncSession, servico_ids: List[int]) -> int:
    """Calcula a duração total em minutos baseada nos IDs dos serviços."""
    if not servico_ids:
        return 30  # Padrão seguro

    stmt = select(Servico.duracao_minutos).where(Servico.id.in_(servico_ids))
    result = await db.execute(stmt)
    duracoes = result.scalars().all()

    # Soma as durações, ignorando nulos, com fallback para 30 se a lista estiver vazia
    total = sum(d for d in duracoes if d)
    return total if total > 0 else 30


def _time_to_minutes(t: time) -> int:
    """Converte objeto time para minutos totais desde o início do dia."""
    return t.hour * 60 + t.minute


async def _checar_conflito(
    db: AsyncSession,
    barbeiro_id: int,
    data: date,
    inicio_min: int,
    fim_min: int,
    exclude_id: Optional[int] = None,
) -> bool:
    """
    Verifica conflito usando matemática simples de minutos.
    Retorna True se houver conflito.
    """
    # Busca apenas os horários e durações dos agendamentos existentes para esse barbeiro/data
    stmt = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.data == data,
        Agendamento.id != exclude_id if exclude_id else True,
    )

    result = await db.execute(stmt)
    ocupados = result.all()

    for occ_hora, occ_duracao in ocupados:
        occ_inicio = _time_to_minutes(occ_hora)
        occ_fim = occ_inicio + (occ_duracao or 30)

        # Lógica de sobreposição: (InicioA < FimB) e (FimA > InicioB)
        if inicio_min < occ_fim and fim_min > occ_inicio:
            return True

    return False


# =============================================================================
# FUNÇÕES PÚBLICAS DO SERVIÇO
# =============================================================================


async def verificar_disponibilidade(
    db: AsyncSession,
    barbeiro_id: int,
    data: date,
    hora_inicio: time,
    duracao_minutos: int = 30,
    exclude_id: Optional[int] = None,
) -> bool:
    """Verifica se um horário está disponível (True = Ocupado/Conflito)."""
    inicio_min = _time_to_minutes(hora_inicio)
    fim_min = inicio_min + duracao_minutos
    return await _checar_conflito(db, barbeiro_id, data, inicio_min, fim_min, exclude_id)


# app/services/agendamento_service.py


async def criar_agendamento(db: AsyncSession, dados: AgendamentoCreate) -> Agendamento:
    """Cria um novo agendamento após verificar disponibilidade e regras de negócio."""

    # 1. Calcular duração total
    duracao_total = await _get_duracao_total(db, dados.servico_ids)

    # 2. Verificar disponibilidade (Conflito de Horário)
    # A função verificar_disponibilidade já deve lidar com objetos time corretamente
    if await verificar_disponibilidade(
        db, dados.barbeiro_id, dados.data, dados.hora, duracao_total
    ):
        raise ValueError("Horário indisponível para a duração selecionada.")

    # 3. ✅ CORREÇÃO CRÍTICA: Validação de Horário de Funcionamento (Ex: Sábado às 12h)
    from app.models.configuracao import Configuracao

    stmt_config = select(Configuracao).limit(1)
    res_config = await db.execute(stmt_config)
    config = res_config.scalars().first()

    if config:
        dia_semana = dados.data.weekday()

        # Definir limite do dia
        if dia_semana == 6:  # Domingo
            raise ValueError("A barbearia não funciona aos domingos.")

        if dia_semana == 5:  # Sábado
            limite_horario = time(12, 0)
        else:
            # Dias de semana: usa o fim da tarde configurado
            limite_horario_str = config.horario_fim_tarde or "18:30"
            # Garante conversão segura
            try:
                limite_horario = datetime.strptime(limite_horario_str, "%H:%M").time()
            except:
                limite_horario = time(18, 30)

        # Calcular horário de término do agendamento
        # dados.hora JÁ É UM OBJETO TIME vindo do schema
        dt_inicio = datetime.combine(dados.data, dados.hora)
        dt_fim = dt_inicio + timedelta(minutes=duracao_total)

        # Tolerância de 5 minutos
        limite_com_tolerancia_dt = datetime.combine(dados.data, limite_horario) + timedelta(
            minutes=5
        )

        if dt_fim > limite_com_tolerancia_dt:
            raise ValueError(
                f"Este serviço ultrapassa o horário de funcionamento ({limite_horario.strftime('%H:%M')}). Escolha um horário mais cedo."
            )

    # 4. Criar objeto base
    novo_agd = Agendamento(
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        data=dados.data,
        hora=dados.hora,  # Objeto time válido
        pago=False,
        is_confirmed=False,
        duracao_minutos=duracao_total,
    )

    # 5. Associar serviços
    if dados.servico_ids:
        stmt = select(Servico).where(Servico.id.in_(dados.servico_ids))
        result = await db.execute(stmt)
        novo_agd.servicos = list(result.scalars().all())

    db.add(novo_agd)
    await db.commit()
    await db.refresh(novo_agd)
    return novo_agd


async def remover_agendamento(db: AsyncSession, agendamento_id: int) -> bool:
    """Remove um agendamento pelo ID."""
    stmt = select(Agendamento).where(Agendamento.id == agendamento_id)
    result = await db.execute(stmt)
    agendamento = result.scalars().first()

    if agendamento:
        await db.delete(agendamento)
        await db.commit()
        return True
    return False


async def confirmar_pagamento_e_baixar_estoque(
    db: AsyncSession,
    agendamento_id: int,
    servico_ids: List[int],
    produtos_qtd: Dict[int, int],
) -> Dict:
    """Confirma pagamento, atualiza serviços/produtos e baixa estoque."""

    # Buscar agendamento
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
            selectinload(Agendamento.produtos),
        )
        .where(Agendamento.id == agendamento_id)
    )

    result = await db.execute(stmt)
    agd = result.scalars().first()

    if not agd:
        raise ValueError("Agendamento não encontrado.")
    if agd.pago:
        raise ValueError("Este agendamento já foi pago.")

    # --- Atualizar Serviços e Duração ---
    agd.servicos.clear()
    duracao_total = await _get_duracao_total(db, servico_ids)

    if servico_ids:
        stmt_serv = select(Servico).where(Servico.id.in_(servico_ids))
        res_serv = await db.execute(stmt_serv)
        agd.servicos = list(res_serv.scalars().all())

    agd.duracao_minutos = duracao_total

    # --- Processar Produtos e Baixar Estoque ---
    total_produtos_val = Decimal("0.00")

    # Limpar associações antigas de produtos
    await db.execute(
        delete(agendamento_produto).where(agendamento_produto.c.agendamento_id == agd.id)
    )

    for prod_id, qtd in produtos_qtd.items():
        if qtd <= 0:
            continue

        stmt_prod = select(Produto).where(Produto.id == prod_id)
        res_prod = await db.execute(stmt_prod)
        produto = res_prod.scalars().first()

        if not produto:
            raise ValueError(f"Produto ID {prod_id} não encontrado.")
        if produto.estoque < qtd:
            raise ValueError(
                f"Estoque insuficiente para '{produto.nome}'. Disponível: {produto.estoque}."
            )

        produto.estoque -= qtd
        total_produtos_val += produto.preco * qtd

        # Insert explícito na tabela associativa com quantidade
        await db.execute(
            insert(agendamento_produto).values(
                agendamento_id=agd.id, produto_id=prod_id, quantidade=qtd
            )
        )

    # --- Finalizar ---
    total_servicos_val = sum(s.preco for s in agd.servicos)
    total_geral = total_servicos_val + total_produtos_val

    agd.pago = True
    agd.is_confirmed = True

    await db.commit()
    await db.refresh(agd)

    return {
        "agendamento": agd,
        "total_geral": float(total_geral),
        "total_servicos": float(total_servicos_val),
        "total_produtos": float(total_produtos_val),
        "duracao_minutos": duracao_total,
    }


async def atualizar_agendamento(
    db: AsyncSession,
    agendamento_id: int,
    nova_data: date,
    nova_hora: time,
    novo_barbeiro_id: int,
    novos_servico_ids: List[int],
) -> Agendamento:
    """Atualiza um agendamento existente com nova data/hora/barbeiro/serviços."""

    # Buscar agendamento
    stmt = select(Agendamento).where(Agendamento.id == agendamento_id)
    result = await db.execute(stmt)
    agd = result.scalars().first()

    if not agd:
        raise ValueError("Agendamento não encontrado.")

    # Calcular nova duração
    duracao_total = await _get_duracao_total(db, novos_servico_ids)

    # Verificar disponibilidade do NOVO horário
    inicio_min = _time_to_minutes(nova_hora)
    fim_min = inicio_min + duracao_total

    if await _checar_conflito(
        db, novo_barbeiro_id, nova_data, inicio_min, fim_min, exclude_id=agendamento_id
    ):
        raise ValueError("Novo horário indisponível para a duração selecionada.")

    # Atualizar dados básicos
    agd.data = nova_data
    agd.hora = nova_hora
    agd.barbeiro_id = novo_barbeiro_id
    agd.duracao_minutos = duracao_total

    # Atualizar serviços (via delete/insert manual para garantir consistência)
    await db.execute(
        delete(agendamento_servico).where(agendamento_servico.c.agendamento_id == agendamento_id)
    )

    if novos_servico_ids:
        for serv_id in novos_servico_ids:
            await db.execute(
                insert(agendamento_servico).values(
                    agendamento_id=agendamento_id, servico_id=serv_id
                )
            )

    await db.commit()
    await db.refresh(agd)
    return agd
