from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Dict
from app.utils.phone_utils import format_phone_for_storage
import re
from app.utils.formatters import format_name

from app.models import Cliente, Barbeiro, Servico, Produto, Agendamento

# ==========================================
# CLIENTES
# ==========================================


async def get_clientes(db: AsyncSession, search: str = None, limit: int = 100):
    query = select(Cliente).order_by(Cliente.nome)
    if search:
        query = query.where(Cliente.nome.ilike(f"%{search}%"))
    query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def get_cliente_com_visitas(db: AsyncSession, cliente_id: int):
    """Retorna um cliente com a contagem de visitas na última semana"""
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    return cliente


async def contar_visitas_ultima_semana(db: AsyncSession, cliente_id: int) -> int:
    """Conta quantas vezes o cliente teve agendamentos na última semana"""
    hoje = date.today()
    sete_dias_atras = hoje - timedelta(days=7)

    stmt = select(func.count(Agendamento.id)).where(
        Agendamento.cliente_id == cliente_id,
        Agendamento.data >= sete_dias_atras,
        Agendamento.data <= hoje,
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def get_clientes_com_visitas(db: AsyncSession):
    """Retorna todos os clientes com a contagem de visitas na última semana"""
    stmt = select(Cliente).order_by(Cliente.nome)
    result = await db.execute(stmt)
    clientes = result.scalars().all()

    clientes_com_visitas = []
    for cliente in clientes:
        visitas = await contar_visitas_ultima_semana(db, cliente.id)
        clientes_com_visitas.append(
            {"cliente": cliente, "visitas_ultima_semana": visitas}
        )

    return clientes_com_visitas


async def criar_cliente(
    db: AsyncSession, nome: str, telefone: str, data_nascimento: date
):
    # ✅ Formatar nome com função utilitária (mais robusto que .title())
    nome_formatado = format_name(nome)

    telefone_padronizado = format_phone_for_storage(telefone)

    # Verifica duplicidade
    stmt_check = select(Cliente).where(
        Cliente.telefone.like(f"%{telefone_padronizado[-9:]}")
    )
    if (await db.execute(stmt_check)).scalars().first():
        raise ValueError("Telefone já cadastrado!")

    novo_cliente = Cliente(
        nome=nome_formatado,  # ← Usa nome formatado pela função utilitária
        telefone=telefone_padronizado,
        data_nascimento=data_nascimento,
        parabens_enviado=False,
    )
    db.add(novo_cliente)
    await db.commit()
    await db.refresh(novo_cliente)
    return novo_cliente


async def atualizar_cliente(
    db: AsyncSession,
    cliente_id: int,
    nome: str,
    telefone: str,
    data_nascimento: date,
):
    # ✅ Formatar nome com função utilitária
    nome_formatado = format_name(nome)

    telefone_padronizado = format_phone_for_storage(telefone)

    stmt = select(Cliente).where(Cliente.id == cliente_id)
    res = await db.execute(stmt)
    cliente = res.scalars().first()

    if not cliente:
        raise ValueError("Cliente não encontrado")

    # Atualizar com valores formatados
    cliente.nome = nome_formatado  # ← Usa nome formatado
    cliente.telefone = telefone_padronizado
    cliente.data_nascimento = data_nascimento

    await db.commit()
    await db.refresh(cliente)

    return cliente


async def excluir_cliente(db: AsyncSession, cliente_id: int):
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    if cliente:
        await db.delete(cliente)
        await db.commit()
        return True
    return False


# ==========================================
# BARBEIROS
# ==========================================


async def get_barbeiros(db: AsyncSession):
    result = await db.execute(select(Barbeiro).order_by(Barbeiro.nome))
    return result.scalars().all()


async def criar_barbeiro(
    db: AsyncSession,
    nome: str,
    telefone: str,
) -> Barbeiro:
    nome_formatado = format_name(nome)
    from app.utils.phone_utils import format_phone_for_storage

    telefone_formatado = format_phone_for_storage(telefone)

    stmt_check = select(Barbeiro).where(Barbeiro.nome.ilike(nome_formatado))
    if (await db.execute(stmt_check)).scalars().first():
        raise ValueError("Barbeiro já cadastrado!")

    novo_barbeiro = Barbeiro(
        nome=nome_formatado,
        telefone=telefone_formatado,
    )

    db.add(novo_barbeiro)
    await db.commit()
    await db.refresh(novo_barbeiro)

    return novo_barbeiro


async def atualizar_barbeiro(
    db: AsyncSession,
    barbeiro_id: int,
    nome: str,
    telefone: str,
) -> Barbeiro:

    nome_formatado = format_name(nome)
    telefone_formatado = format_phone_for_storage(telefone)

    stmt = select(Barbeiro).where(Barbeiro.id == barbeiro_id)
    res = await db.execute(stmt)
    barbeiro = res.scalars().first()

    if not barbeiro:
        raise ValueError("Barbeiro não encontrado")

    barbeiro.nome = nome_formatado
    barbeiro.telefone = telefone_formatado

    await db.commit()
    await db.refresh(barbeiro)

    return barbeiro


async def excluir_barbeiro(db: AsyncSession, barbeiro_id: int):
    stmt = select(Barbeiro).where(Barbeiro.id == barbeiro_id)
    result = await db.execute(stmt)
    barbeiro = result.scalars().first()
    if barbeiro:
        await db.delete(barbeiro)
        await db.commit()
        return True
    return False


# ==========================================
# SERVIÇOS (CORTES)
# ==========================================


async def get_servicos(db: AsyncSession):
    result = await db.execute(select(Servico).order_by(Servico.nome))
    return result.scalars().all()


async def criar_servico(
    db: AsyncSession,
    nome: str,
    preco: float,
    duracao_minutos: int = None,
) -> Servico:
    """Cria um novo serviço com nome padronizado"""

    nome_formatado = format_name(nome)

    stmt_check = select(Servico).where(Servico.nome.ilike(nome_formatado))
    if (await db.execute(stmt_check)).scalars().first():
        raise ValueError("Serviço já cadastrado!")

    novo_servico = Servico(
        nome=nome_formatado,  # ← ✅ Nome formatado
        preco=preco,
        duracao_minutos=duracao_minutos,
    )

    db.add(novo_servico)
    await db.commit()
    await db.refresh(novo_servico)

    return novo_servico


async def atualizar_servico(
    db: AsyncSession,
    servico_id: int,
    nome: str,
    preco: float,
    duracao_minutos: int = None,
) -> Servico:
    """Atualiza serviço com nome padronizado"""

    nome_formatado = format_name(nome)

    stmt = select(Servico).where(Servico.id == servico_id)
    res = await db.execute(stmt)
    servico = res.scalars().first()

    if not servico:
        raise ValueError("Serviço não encontrado")

    servico.nome = nome_formatado
    servico.preco = preco
    if duracao_minutos is not None:
        servico.duracao_minutos = duracao_minutos

    await db.commit()
    await db.refresh(servico)

    return servico


async def excluir_servico(db: AsyncSession, servico_id: int):
    stmt = select(Servico).where(Servico.id == servico_id)
    result = await db.execute(stmt)
    servico = result.scalars().first()
    if servico:
        await db.delete(servico)
        await db.commit()
        return True
    return False


# ==========================================
# PRODUTOS
# ==========================================


async def get_produtos(db: AsyncSession):
    result = await db.execute(select(Produto).order_by(Produto.nome))
    return result.scalars().all()


async def criar_produto(
    db: AsyncSession,
    nome: str,
    preco: float,
    estoque: int = 0,
    descricao: str = None,
) -> Produto:

    nome_formatado = format_name(nome)

    # Verificar duplicidade
    stmt_check = select(Produto).where(Produto.nome.ilike(nome_formatado))
    if (await db.execute(stmt_check)).scalars().first():
        raise ValueError("Produto já cadastrado!")

    novo_produto = Produto(
        nome=nome_formatado,
        preco=preco,
        estoque=estoque,
        descricao=descricao,
    )

    db.add(novo_produto)
    await db.commit()
    await db.refresh(novo_produto)

    return novo_produto


async def atualizar_produto(
    db: AsyncSession,
    produto_id: int,
    nome: str,
    preco: float,
    estoque: int = None,
    descricao: str = None,
) -> Produto:
    """Atualiza produto com nome padronizado"""

    nome_formatado = format_name(nome)

    stmt = select(Produto).where(Produto.id == produto_id)
    res = await db.execute(stmt)
    produto = res.scalars().first()

    if not produto:
        raise ValueError("Produto não encontrado")

    produto.nome = nome_formatado
    produto.preco = preco
    if estoque is not None:
        produto.estoque = estoque
    if descricao is not None:
        produto.descricao = descricao

    await db.commit()
    await db.refresh(produto)

    return produto


async def excluir_produto(db: AsyncSession, produto_id: int):
    stmt = select(Produto).where(Produto.id == produto_id)
    result = await db.execute(stmt)
    produto = result.scalars().first()
    if produto:
        await db.delete(produto)
        await db.commit()
        return True
    return False


# ==========================================
# ESTATÍSTICAS GERAIS
# ==========================================


async def get_estatisticas_gerais(db: AsyncSession, data_inicio: date, data_fim: date):
    # Receita Total de Cortes no Período
    # Usamos func.sum() corretamente
    query_receita_cortes = (
        select(func.sum(Servico.preco))
        .select_from(Agendamento)
        .join(Agendamento.servicos)
        .where(
            Agendamento.pago == True,
            Agendamento.data >= data_inicio,
            Agendamento.data <= data_fim,
        )
    )
    res_rec = await db.execute(query_receita_cortes)
    receita_cortes = res_rec.scalar() or Decimal("0.00")

    # Receita de Produtos (Estimativa baseada no preço atual do produto vinculado)
    # Nota: Em um sistema real de histórico, deveríamos salvar o preço no momento da venda.
    # Aqui, somamos o preço atual dos produtos vinculados aos agendamentos pagos.
    query_receita_produtos = (
        select(func.sum(Produto.preco))
        .select_from(Agendamento)
        .join(Agendamento.produtos)
        .where(
            Agendamento.pago == True,
            Agendamento.data >= data_inicio,
            Agendamento.data <= data_fim,
        )
    )
    res_prod = await db.execute(query_receita_produtos)
    receita_produtos = res_prod.scalar() or Decimal("0.00")

    return {
        "receita_cortes": receita_cortes,
        "receita_produtos": receita_produtos,
        "receita_total": receita_cortes + receita_produtos,
    }
