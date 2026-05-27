from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert, delete, and_, or_
from sqlalchemy.orm import selectinload
from datetime import date, time, datetime, timedelta
from typing import List, Optional, Dict
from decimal import Decimal

from app.models.agendamento import Agendamento
from app.models.servico import Servico
from app.models.produto import Produto, agendamento_produto
from app.models.cliente import Cliente
from app.models.barbeiro import Barbeiro
from app.schemas.agendamento import AgendamentoCreate


async def verificar_disponibilidade(
    db: AsyncSession,
    barbeiro_id: int,
    data: date,
    hora_inicio: time,
    duracao_minutos: int = 30,
    exclude_id: Optional[int] = None,
) -> bool:
    """
    Verifica se há conflito de horário considerando a DURAÇÃO do serviço.
    Retorna True se ESTÁ OCUPADO, False se está livre.
    """
    from sqlalchemy import and_, or_

    # Calcula o intervalo do novo agendamento
    dt_inicio = datetime.combine(data, hora_inicio)
    dt_fim = dt_inicio + timedelta(minutes=duracao_minutos)

    # Busca agendamentos que se SOBREPÕEM com este intervalo
    # Lógica: [inicio_novo, fim_novo) intersect [inicio_existente, fim_existente) ≠ ∅
    stmt = select(Agendamento).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.data == data,
        Agendamento.id != exclude_id if exclude_id else True,
        # Sobreposição: começa antes do fim do novo E termina depois do início do novo
        Agendamento.hora < dt_fim.time(),
        # Para calcular fim_existente, usamos duracao_minutos do agendamento ou padrão 30
        # Se sua tabela agendamentos já tem duracao_minutos, use:
        # (Agendamento.hora + timedelta(minutes=Agendamento.duracao_minutos)) > dt_inicio.time()
        # Por enquanto, usamos 30min como fallback:
        (Agendamento.hora + timedelta(minutes=30)) > dt_inicio.time(),
    )

    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def criar_agendamento(db: AsyncSession, dados: AgendamentoCreate):
    """
    Cria um novo agendamento com verificação de disponibilidade considerando duração.
    """
    # Calcular duração total dos serviços selecionados
    duracao_total = 30  # Valor padrão
    if dados.servico_ids and len(dados.servico_ids) > 0:
        stmt_serv = select(Servico).where(Servico.id.in_(dados.servico_ids))
        result_serv = await db.execute(stmt_serv)
        servicos_sel = result_serv.scalars().all()
        duracao_total = (
            sum(s.duracao_minutos for s in servicos_sel if s.duracao_minutos) or 30
        )

    # Verificar disponibilidade COM a duração calculada
    ocupado = await verificar_disponibilidade(
        db,
        dados.barbeiro_id,
        dados.data,
        dados.hora,
        duracao_minutos=duracao_total,  # ← Passa a duração para verificação
    )
    if ocupado:
        raise ValueError("Horário indisponível para a duração selecionada.")

    # Criar agendamento
    novo_agd = Agendamento(
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        data=dados.data,
        hora=dados.hora,
        pago=False,
        is_confirmed=False,
        duracao_minutos=duracao_total,  # ← Salva a duração usada
    )

    # Associar serviços
    if dados.servico_ids and len(dados.servico_ids) > 0:
        stmt = select(Servico).where(Servico.id.in_(dados.servico_ids))
        result = await db.execute(stmt)
        novo_agd.servicos = result.scalars().all()

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
):
    """
    Confirma pagamento, atualiza serviços/produtos e baixa estoque.
    Mantém a duração calculada com base nos novos serviços.
    """
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

    # 🔹 Atualizar Serviços e recalcular duração
    agd.servicos.clear()
    duracao_total = 30

    if servico_ids and len(servico_ids) > 0:
        stmt_serv = select(Servico).where(Servico.id.in_(servico_ids))
        res_serv = await db.execute(stmt_serv)
        for s in res_serv.scalars().all():
            agd.servicos.append(s)
            duracao_total += s.duracao_minutos or 30

    # Atualiza a duração no agendamento
    agd.duracao_minutos = duracao_total

    # 🔹 Processar Produtos com INSERT MANUAL para garantir quantidade
    total_produtos_val = Decimal("0.00")

    # Limpar associações antigas de produtos
    await db.execute(
        delete(agendamento_produto).where(
            agendamento_produto.c.agendamento_id == agd.id
        )
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

    # 🔹 Calcular totais
    total_servicos_val = sum(s.preco for s in agd.servicos)
    total_geral = total_servicos_val + total_produtos_val

    # 🔹 Marcar como pago e confirmado
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
    """
    Atualiza um agendamento existente com nova data/hora/barbeiro/serviços.
    Inclui verificação de disponibilidade com duração dinâmica.
    """
    # Buscar agendamento
    stmt = select(Agendamento).where(Agendamento.id == agendamento_id)
    result = await db.execute(stmt)
    agd = result.scalars().first()

    if not agd:
        raise ValueError("Agendamento não encontrado.")

    # Calcular nova duração
    duracao_total = 30
    if novos_servico_ids:
        stmt_serv = select(Servico).where(Servico.id.in_(novos_servico_ids))
        res_serv = await db.execute(stmt_serv)
        servicos_sel = res_serv.scalars().all()
        duracao_total = (
            sum(s.duracao_minutos for s in servicos_sel if s.duracao_minutos) or 30
        )

    # Verificar disponibilidade do NOVO horário com a NOVA duração
    ocupado = await verificar_disponibilidade(
        db,
        novo_barbeiro_id,
        nova_data,
        nova_hora,
        duracao_minutos=duracao_total,
        exclude_id=agendamento_id,  # Exclui o próprio agendamento da verificação
    )
    if ocupado:
        raise ValueError("Novo horário indisponível para a duração selecionada.")

    # Atualizar dados
    agd.data = nova_data
    agd.hora = nova_hora
    agd.barbeiro_id = novo_barbeiro_id
    agd.duracao_minutos = duracao_total

    # Atualizar serviços (via tabela associativa para evitar greenlet_spawn)
    await db.execute(
        delete(app.models.servico.agendamento_servico).where(
            app.models.servico.agendamento_servico.c.agendamento_id == agendamento_id
        )
    )
    if novos_servico_ids:
        from app.models.servico import agendamento_servico

        for serv_id in novos_servico_ids:
            await db.execute(
                insert(agendamento_servico).values(
                    agendamento_id=agendamento_id, servico_id=serv_id
                )
            )

    await db.commit()
    await db.refresh(agd)
    return agd
