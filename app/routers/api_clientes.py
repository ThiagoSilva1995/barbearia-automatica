"""
API REST - Clientes
===================

Endpoints REST para gerenciamento de clientes da barbearia.
Documentação completa disponível em /docs (Swagger UI)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import date

from app.database import get_db
from app.models import Cliente
from app.schemas.cliente import ClienteCreate, ClienteResponse, ClienteUpdate
from app.utils.phone_utils import format_phone_for_storage

router = APIRouter(
    prefix="/api/clientes",
    tags=["👤 Clientes"],
    responses={
        404: {"description": "Cliente não encontrado"},
        500: {"description": "Erro interno do servidor"}
    }
)


@router.get(
    "/",
    response_model=List[ClienteResponse],
    summary="Listar todos os clientes",
    description="Retorna uma lista de todos os clientes cadastrados no sistema, ordenados alfabeticamente por nome.",
    response_description="Lista de clientes com ID, nome, telefone, data de nascimento e status de aniversário"
)
async def listar_clientes(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Número de registros para pular (paginação)"),
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de registros a retornar")
):
    """
    Lista todos os clientes cadastrados.
    
    - **skip**: Quantos registros pular (útil para paginação)
    - **limit**: Máximo de registros a retornar (1-1000)
    
    Retorna lista de clientes ordenados por nome.
    """
    stmt = select(Cliente).offset(skip).limit(limit).order_by(Cliente.nome)
    result = await db.execute(stmt)
    clientes = result.scalars().all()
    return clientes


@router.get(
    "/{cliente_id}",
    response_model=ClienteResponse,
    summary="Buscar cliente por ID",
    description="Retorna os dados completos de um cliente específico baseado no seu ID.",
    response_description="Dados completos do cliente"
)
async def buscar_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Busca um cliente específico pelo ID.
    
    - **cliente_id**: ID único do cliente
    
    Retorna os dados completos do cliente ou erro 404 se não encontrado.
    """
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {cliente_id} não encontrado"
        )
    
    return cliente


@router.get(
    "/telefone/{telefone}",
    response_model=List[ClienteResponse],
    summary="Buscar cliente por telefone",
    description="Busca clientes pelo número de telefone. Aceita qualquer formatação e normaliza automaticamente.",
    response_description="Lista de clientes encontrados (pode retornar múltiplos se houver duplicatas)"
)
async def buscar_cliente_telefone(
    telefone: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Busca cliente(s) pelo telefone.
    
    - **telefone**: Número de telefone (aceita qualquer formatação)
    
    O sistema normaliza o telefone e faz busca flexível.
    Pode retornar múltiplos clientes se houver duplicatas.
    """
    telefone_normalizado = format_phone_for_storage(telefone)
    
    stmt = select(Cliente).where(Cliente.telefone.like(f"%{telefone_normalizado}"))
    result = await db.execute(stmt)
    clientes = result.scalars().all()
    
    if not clientes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhum cliente encontrado com telefone {telefone}"
        )
    
    return clientes


@router.get(
    "/aniversariantes/{mes}/{dia}",
    response_model=List[ClienteResponse],
    summary="Buscar aniversariantes do dia",
    description="Retorna todos os clientes que fazem aniversário em um determinado dia e mês.",
    response_description="Lista de clientes aniversariantes"
)
async def buscar_aniversariantes(
    mes: int = Query(..., ge=1, le=12, description="Mês (1-12)"),
    dia: int = Query(..., ge=1, le=31, description="Dia (1-31)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Busca clientes que fazem aniversário em uma data específica.
    
    - **mes**: Mês do aniversário (1-12)
    - **dia**: Dia do aniversário (1-31)
    
    Útil para enviar mensagens de aniversário automáticas.
    """
    stmt = select(Cliente).where(
        Cliente.data_nascimento != None
    )
    
    result = await db.execute(stmt)
    todos_clientes = result.scalars().all()
    
    aniversariantes = [
        c for c in todos_clientes
        if c.data_nascimento.month == mes and c.data_nascimento.day == dia
    ]
    
    return aniversariantes


@router.post(
    "/",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar novo cliente",
    description="Cadastra um novo cliente no sistema. O telefone será normalizado automaticamente.",
    response_description="Cliente criado com sucesso"
)
async def criar_cliente(
    cliente: ClienteCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Cria um novo cliente.
    
    - **nome**: Nome completo do cliente (mínimo 3 caracteres)
    - **telefone**: Número de telefone (10-15 dígitos)
    - **data_nascimento**: Data de nascimento no formato YYYY-MM-DD
    
    O telefone será normalizado para o formato internacional (5573999999999).
    """
    # Verificar se já existe cliente com mesmo telefone
    telefone_normalizado = format_phone_for_storage(cliente.telefone)
    
    stmt = select(Cliente).where(Cliente.telefone == telefone_normalizado)
    result = await db.execute(stmt)
    existente = result.scalars().first()
    
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Já existe um cliente cadastrado com o telefone {telefone_normalizado}"
        )
    
    # Criar novo cliente
    novo_cliente = Cliente(
        nome=cliente.nome,
        telefone=telefone_normalizado,
        data_nascimento=cliente.data_nascimento,
        parabens_enviado=False
    )
    
    db.add(novo_cliente)
    await db.commit()
    await db.refresh(novo_cliente)
    
    return novo_cliente


@router.put(
    "/{cliente_id}",
    response_model=ClienteResponse,
    summary="Atualizar cliente",
    description="Atualiza os dados de um cliente existente. Todos os campos são opcionais.",
    response_description="Cliente atualizado com sucesso"
)
async def atualizar_cliente(
    cliente_id: int,
    cliente_update: ClienteUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Atualiza um cliente existente.
    
    - **cliente_id**: ID do cliente a ser atualizado
    - **nome**: Novo nome (opcional)
    - **telefone**: Novo telefone (opcional, será normalizado)
    - **data_nascimento**: Nova data de nascimento (opcional)
    
    Apenas os campos fornecidos serão atualizados.
    """
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {cliente_id} não encontrado"
        )
    
    # Atualizar apenas campos fornecidos
    if cliente_update.nome is not None:
        cliente.nome = cliente_update.nome
    
    if cliente_update.telefone is not None:
        telefone_normalizado = format_phone_for_storage(cliente_update.telefone)
        
        # Verificar se novo telefone já existe
        stmt_check = select(Cliente).where(
            Cliente.telefone == telefone_normalizado,
            Cliente.id != cliente_id
        )
        result_check = await db.execute(stmt_check)
        if result_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe outro cliente com o telefone {telefone_normalizado}"
            )
        
        cliente.telefone = telefone_normalizado
    
    if cliente_update.data_nascimento is not None:
        cliente.data_nascimento = cliente_update.data_nascimento
    
    await db.commit()
    await db.refresh(cliente)
    
    return cliente


@router.delete(
    "/{cliente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir cliente",
    description="Remove permanentemente um cliente do sistema. Atenção: Esta ação não pode ser desfeita.",
    response_description="Cliente excluído com sucesso"
)
async def excluir_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Exclui um cliente permanentemente.
    
    - **cliente_id**: ID do cliente a ser excluído
    
    ⚠️ **ATENÇÃO**: Esta ação não pode ser desfeita.
    Se o cliente tiver agendamentos, considere desativar em vez de excluir.
    """
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {cliente_id} não encontrado"
        )
    
    await db.delete(cliente)
    await db.commit()
    
    return None


@router.patch(
    "/{cliente_id}/aniversario",
    response_model=ClienteResponse,
    summary="Marcar aniversário como enviado",
    description="Marca que a mensagem de aniversário já foi enviada para este cliente (evita spam).",
    response_description="Cliente com flag de aniversário atualizada"
)
async def marcar_aniversario_enviado(
    cliente_id: int,
    enviado: bool = Query(True, description="True para marcar como enviado, False para resetar"),
    db: AsyncSession = Depends(get_db)
):
    """
    Marca ou reseta o status de envio de aniversário.
    
    - **cliente_id**: ID do cliente
    - **enviado**: True para marcar como enviado, False para resetar
    
    Útil para controlar o envio automático de mensagens de aniversário.
    """
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {cliente_id} não encontrado"
        )
    
    cliente.parabens_enviado = enviado
    await db.commit()
    await db.refresh(cliente)
    
    return cliente
