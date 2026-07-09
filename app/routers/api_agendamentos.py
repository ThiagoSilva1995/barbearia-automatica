"""
API REST - Agendamentos
========================

Endpoints REST para gerenciamento de agendamentos da barbearia.
Documentação completa disponível em /docs (Swagger UI)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import date, datetime, time

from app.database import get_db
from app.models import Agendamento, Cliente, Barbeiro, Servico
from app.schemas.agendamento import AgendamentoCreate, AgendamentoResponse, AgendamentoUpdate
from app.services.agendamento_service import (
    criar_agendamento,
    remover_agendamento,
    confirmar_pagamento_e_baixar_estoque,
)

router = APIRouter(
    prefix="/api/agendamentos",
    tags=["📅 Agendamentos"],
    responses={
        404: {"description": "Agendamento não encontrado"},
        409: {"description": "Conflito de horário"},
        500: {"description": "Erro interno do servidor"}
    }
)


@router.get(
    "/",
    response_model=List[AgendamentoResponse],
    summary="Listar agendamentos",
    description="Retorna lista de agendamentos com filtros opcionais por data e barbeiro.",
    response_description="Lista de agendamentos encontrados"
)
async def listar_agendamentos(
    data: Optional[date] = Query(None, description="Filtrar por data específica (YYYY-MM-DD)"),
    barbeiro_id: Optional[int] = Query(None, description="Filtrar por ID do barbeiro"),
    pago: Optional[bool] = Query(None, description="Filtrar por status de pagamento"),
    skip: int = Query(0, ge=0, description="Número de registros para pular"),
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de registros"),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista agendamentos com filtros opcionais.
    
    - **data**: Filtrar por data específica (formato YYYY-MM-DD)
    - **barbeiro_id**: Filtrar por ID do barbeiro
    - **pago**: Filtrar por status de pagamento (True/False)
    - **skip**: Quantos registros pular (paginação)
    - **limit**: Máximo de registros a retornar (1-1000)
    
    Retorna lista de agendamentos ordenados por data e hora.
    """
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .offset(skip)
        .limit(limit)
    )
    
    # Aplicar filtros
    if data:
        stmt = stmt.where(Agendamento.data == data)
    
    if barbeiro_id:
        stmt = stmt.where(Agendamento.barbeiro_id == barbeiro_id)
    
    if pago is not None:
        stmt = stmt.where(Agendamento.pago == pago)
    
    stmt = stmt.order_by(Agendamento.data.desc(), Agendamento.hora.desc())
    
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()
    
    return agendamentos


@router.get(
    "/{agendamento_id}",
    response_model=AgendamentoResponse,
    summary="Buscar agendamento por ID",
    description="Retorna os dados completos de um agendamento específico.",
    response_description="Dados completos do agendamento"
)
async def buscar_agendamento(
    agendamento_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Busca um agendamento específico pelo ID.
    
    - **agendamento_id**: ID único do agendamento
    
    Retorna dados completos incluindo cliente, barbeiro e serviços.
    """
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.id == agendamento_id)
    )
    
    result = await db.execute(stmt)
    agendamento = result.scalars().first()
    
    if not agendamento:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {agendamento_id} não encontrado"
        )
    
    return agendamento


@router.get(
    "/cliente/{cliente_id}",
    response_model=List[AgendamentoResponse],
    summary="Listar agendamentos de um cliente",
    description="Retorna todos os agendamentos de um cliente específico, ordenados por data.",
    response_description="Lista de agendamentos do cliente"
)
async def listar_agendamentos_cliente(
    cliente_id: int,
    futuros: bool = Query(False, description="Se True, retorna apenas agendamentos futuros"),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista todos os agendamentos de um cliente.
    
    - **cliente_id**: ID do cliente
    - **futuros**: Se True, retorna apenas agendamentos futuros (data >= hoje)
    
    Retorna lista de agendamentos ordenados por data (mais recentes primeiro).
    """
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.cliente_id == cliente_id)
    )
    
    if futuros:
        hoje = datetime.now().date()
        stmt = stmt.where(Agendamento.data >= hoje)
    
    stmt = stmt.order_by(Agendamento.data.desc(), Agendamento.hora.desc())
    
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()
    
    return agendamentos


@router.get(
    "/barbeiro/{barbeiro_id}",
    response_model=List[AgendamentoResponse],
    summary="Listar agendamentos de um barbeiro",
    description="Retorna todos os agendamentos de um barbeiro específico em uma data.",
    response_description="Lista de agendamentos do barbeiro"
)
async def listar_agendamentos_barbeiro(
    barbeiro_id: int,
    data: date = Query(..., description="Data para buscar agendamentos (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista agendamentos de um barbeiro em uma data específica.
    
    - **barbeiro_id**: ID do barbeiro
    - **data**: Data para buscar (formato YYYY-MM-DD)
    
    Retorna lista de agendamentos ordenados por hora.
    """
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.servicos),
        )
        .where(
            Agendamento.barbeiro_id == barbeiro_id,
            Agendamento.data == data
        )
        .order_by(Agendamento.hora)
    )
    
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()
    
    return agendamentos


@router.post(
    "/",
    response_model=AgendamentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar novo agendamento",
    description="Cria um novo agendamento com validação de disponibilidade e horário de funcionamento.",
    response_description="Agendamento criado com sucesso"
)
async def criar_novo_agendamento(
    agendamento: AgendamentoCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Cria um novo agendamento.
    
    - **cliente_id**: ID do cliente
    - **barbeiro_id**: ID do barbeiro
    - **data**: Data do agendamento (YYYY-MM-DD)
    - **hora**: Horário de início (HH:MM)
    - **servico_ids**: Lista de IDs dos serviços
    - **produto_ids**: Lista de IDs dos produtos (opcional)
    
    O sistema valida:
    - Disponibilidade do horário (sem conflitos)
    - Horário de funcionamento da barbearia
    - Duração total dos serviços
    
    Retorna erro 409 se houver conflito de horário.
    """
    try:
        novo_agendamento = await criar_agendamento(db, agendamento)
        return novo_agendamento
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar agendamento: {str(e)}"
        )


@router.put(
    "/{agendamento_id}",
    response_model=AgendamentoResponse,
    summary="Atualizar agendamento",
    description="Atualiza os dados de um agendamento existente com validação de disponibilidade.",
    response_description="Agendamento atualizado com sucesso"
)
async def atualizar_agendamento(
    agendamento_id: int,
    agendamento_update: AgendamentoUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Atualiza um agendamento existente.
    
    - **agendamento_id**: ID do agendamento a ser atualizado
    - **cliente_id**: Novo ID do cliente (opcional)
    - **barbeiro_id**: Novo ID do barbeiro (opcional)
    - **data**: Nova data (opcional, YYYY-MM-DD)
    - **hora**: Novo horário (opcional, HH:MM)
    - **servico_ids**: Nova lista de serviços (opcional)
    
    Apenas os campos fornecidos serão atualizados.
    O sistema valida disponibilidade se data/hora/barbeiro forem alterados.
    """
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.id == agendamento_id)
    )
    
    result = await db.execute(stmt)
    agendamento = result.scalars().first()
    
    if not agendamento:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {agendamento_id} não encontrado"
        )
    
    # Atualizar campos fornecidos
    if agendamento_update.cliente_id is not None:
        agendamento.cliente_id = agendamento_update.cliente_id
    
    if agendamento_update.barbeiro_id is not None:
        agendamento.barbeiro_id = agendamento_update.barbeiro_id
    
    if agendamento_update.data is not None:
        agendamento.data = agendamento_update.data
    
    if agendamento_update.hora is not None:
        agendamento.hora = agendamento_update.hora
    
    if agendamento_update.pago is not None:
        agendamento.pago = agendamento_update.pago
    
    await db.commit()
    await db.refresh(agendamento)
    
    return agendamento


@router.delete(
    "/{agendamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancelar agendamento",
    description="Remove permanentemente um agendamento do sistema.",
    response_description="Agendamento cancelado com sucesso"
)
async def cancelar_agendamento(
    agendamento_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Cancela um agendamento permanentemente.
    
    - **agendamento_id**: ID do agendamento a ser cancelado
    
    ⚠️ **ATENÇÃO**: Esta ação não pode ser desfeita.
    """
    sucesso = await remover_agendamento(db, agendamento_id)
    
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {agendamento_id} não encontrado"
        )
    
    return None


@router.post(
    "/{agendamento_id}/pagar",
    response_model=AgendamentoResponse,
    summary="Confirmar pagamento",
    description="Confirma o pagamento de um agendamento e baixa estoque de produtos vendidos.",
    response_description="Pagamento confirmado com sucesso"
)
async def confirmar_pagamento(
    agendamento_id: int,
    servico_ids: List[int] = Query(..., description="Lista de IDs dos serviços cobrados"),
    produtos_qtd: Optional[dict] = Query(None, description="Dicionário {produto_id: quantidade}"),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirma o pagamento de um agendamento.
    
    - **agendamento_id**: ID do agendamento
    - **servico_ids**: Lista de IDs dos serviços cobrados
    - **produtos_qtd**: Dicionário com quantidade de produtos vendidos (opcional)
    
    O sistema:
    - Marca o agendamento como pago
    - Baixa estoque dos produtos vendidos
    - Calcula valor total
    
    Retorna erro 404 se agendamento não encontrado ou já pago.
    """
    try:
        resultado = await confirmar_pagamento_e_baixar_estoque(
            db, agendamento_id, servico_ids, produtos_qtd or {}
        )
        
        # Buscar agendamento atualizado
        stmt = (
            select(Agendamento)
            .options(
                selectinload(Agendamento.cliente),
                selectinload(Agendamento.barbeiro),
                selectinload(Agendamento.servicos),
            )
            .where(Agendamento.id == agendamento_id)
        )
        result = await db.execute(stmt)
        agendamento = result.scalars().first()
        
        return agendamento
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao confirmar pagamento: {str(e)}"
        )


@router.get(
    "/hoje",
    response_model=List[AgendamentoResponse],
    summary="Listar agendamentos de hoje",
    description="Retorna todos os agendamentos do dia atual, ordenados por horário.",
    response_description="Lista de agendamentos de hoje"
)
async def listar_agendamentos_hoje(
    db: AsyncSession = Depends(get_db)
):
    """
    Lista todos os agendamentos do dia atual.
    
    Retorna lista de agendamentos de hoje ordenados por hora.
    """
    hoje = datetime.now().date()
    
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.data == hoje)
        .order_by(Agendamento.hora)
    )
    
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()
    
    return agendamentos


@router.get(
    "/semana",
    response_model=List[AgendamentoResponse],
    summary="Listar agendamentos da semana",
    description="Retorna todos os agendamentos dos próximos 7 dias.",
    response_description="Lista de agendamentos da semana"
)
async def listar_agendamentos_semana(
    db: AsyncSession = Depends(get_db)
):
    """
    Lista todos os agendamentos dos próximos 7 dias.
    
    Retorna lista de agendamentos ordenados por data e hora.
    """
    hoje = datetime.now().date()
    from datetime import timedelta
    semana_que_vem = hoje + timedelta(days=7)
    
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(
            Agendamento.data >= hoje,
            Agendamento.data <= semana_que_vem
        )
        .order_by(Agendamento.data, Agendamento.hora)
    )
    
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()
    
    return agendamentos
