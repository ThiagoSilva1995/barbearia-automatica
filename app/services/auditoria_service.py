from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.auditoria import AuditoriaAgendamento
from app.models.agendamento import Agendamento
from app.models.cliente import Cliente
from app.models.barbeiro import Barbeiro
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)
tz_br = pytz.timezone("America/Sao_Paulo")


async def registrar_auditoria(
    db: AsyncSession,
    acao: str,
    agendamento: Agendamento = None,
    agendamento_id: int = None,
    usuario_tipo: str = "sistema",
    usuario_id: int = None,
    usuario_nome: str = None,
    detalhes: dict = None,
    ip_origem: str = None
):
    """Registra uma operação na tabela de auditoria"""
    try:
        # Buscar dados do agendamento se fornecido
        cliente_nome = None
        barbeiro_nome = None
        data_agd = None
        hora_agd = None
        servicos = None
        
        if agendamento:
            agendamento_id = agendamento.id
            data_agd = agendamento.data.isoformat() if agendamento.data else None
            hora_agd = agendamento.hora.strftime("%H:%M") if agendamento.hora else None
            
            # Buscar nomes relacionados
            if agendamento.cliente_id:
                result = await db.execute(
                    select(Cliente).where(Cliente.id == agendamento.cliente_id)
                )
                cliente = result.scalar_one_or_none()
                if cliente:
                    cliente_nome = cliente.nome
            
            if agendamento.barbeiro_id:
                result = await db.execute(
                    select(Barbeiro).where(Barbeiro.id == agendamento.barbeiro_id)
                )
                barbeiro = result.scalar_one_or_none()
                if barbeiro:
                    barbeiro_nome = barbeiro.nome
            
            if agendamento.servicos:
                servicos = agendamento.servicos
        
        auditoria = AuditoriaAgendamento(
            agendamento_id=agendamento_id,
            acao=acao,
            usuario_tipo=usuario_tipo,
            usuario_id=usuario_id,
            usuario_nome=usuario_nome,
            cliente_nome=cliente_nome,
            barbeiro_nome=barbeiro_nome,
            data_agendamento=data_agd,
            hora_agendamento=hora_agd,
            servicos=servicos,
            detalhes=detalhes,
            ip_origem=ip_origem
        )
        
        db.add(auditoria)
        await db.commit()
        logger.info(f"✅ Auditoria registrada: {acao} (agendamento={agendamento_id})")
        return auditoria
        
    except Exception as e:
        logger.error(f"❌ Erro ao registrar auditoria: {e}")
        # Não quebrar a operação principal se a auditoria falhar
        await db.rollback()
        return None


async def buscar_auditoria(
    db: AsyncSession,
    data_inicio: datetime = None,
    data_fim: datetime = None,
    acao: str = None,
    agendamento_id: int = None,
    limite: int = 100
):
    """Busca registros de auditoria com filtros"""
    query = select(AuditoriaAgendamento)
    
    if data_inicio:
        query = query.where(AuditoriaAgendamento.criada_em >= data_inicio)
    if data_fim:
        query = query.where(AuditoriaAgendamento.criada_em <= data_fim)
    if acao:
        query = query.where(AuditoriaAgendamento.acao == acao)
    if agendamento_id:
        query = query.where(AuditoriaAgendamento.agendamento_id == agendamento_id)
    
    query = query.order_by(AuditoriaAgendamento.criada_em.desc()).limit(limite)
    
    result = await db.execute(query)
    return result.scalars().all()
