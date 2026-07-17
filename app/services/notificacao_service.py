from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notificacao import Notificacao
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class NotificacaoService:
    """Serviço para gerenciar notificações in-app"""
    
    @staticmethod
    async def criar_notificacao(
        db: AsyncSession,
        tipo: str,
        titulo: str,
        mensagem: str = None,
        icone: str = "🔔",
        cor: str = "red",
        link: str = None,
        agendamento_id: int = None,
        data_agendamento: str = None,
        dados_extra: dict = None
    ) -> Notificacao:
        """Cria uma nova notificação"""
        try:
            notificacao = Notificacao(
                tipo=tipo,
                titulo=titulo,
                mensagem=mensagem,
                icone=icone,
                cor=cor,
                link=link,
                agendamento_id=agendamento_id,
                data_agendamento=data_agendamento,
                dados_extra=json.dumps(dados_extra) if dados_extra else None
            )
            db.add(notificacao)
            await db.commit()
            await db.refresh(notificacao)
            logger.info(f"✅ Notificação criada: {titulo}")
            return notificacao
        except Exception as e:
            logger.error(f"❌ Erro ao criar notificação: {e}")
            await db.rollback()
            return None
    
    @staticmethod
    async def criar_notificacao_agendamento(
        db: AsyncSession,
        agendamento,
        cliente_nome: str,
        barbeiro_nome: str,
        servicos_nomes: list,
        acao: str = "criado"  # criado, alterado, cancelado
    ) -> Notificacao:
        """Cria notificação para agendamento (novo, alterado ou cancelado)"""
        try:
            # Definir ícone, cor e título baseado na ação
            if acao == "criado":
                icone = "✅"
                cor = "green"
                titulo = f"Novo Agendamento: {cliente_nome}"
            elif acao == "alterado":
                icone = "🔄"
                cor = "blue"
                titulo = f"Agendamento Alterado: {cliente_nome}"
            elif acao == "cancelado":
                icone = "❌"
                cor = "red"
                titulo = f"Agendamento Cancelado: {cliente_nome}"
            else:
                icone = "🔔"
                cor = "gray"
                titulo = f"Agendamento: {cliente_nome}"
            
            # Formatar data e hora
            data_str = agendamento.data.strftime("%d/%m/%Y")
            hora_str = agendamento.hora.strftime("%H:%M")
            
            # Criar mensagem detalhada
            mensagem = f"""
👤 Cliente: {cliente_nome}
💇 Barbeiro: {barbeiro_nome}
📅 Data: {data_str} às {hora_str}
✂️ Serviços: {', '.join(servicos_nomes)}
            """.strip()
            
            # Link para redirecionamento
            data_iso = agendamento.data.strftime("%Y-%m-%d")
            link = f"/agendamentos?data={data_iso}&destaque={agendamento.id}"
            
            return await NotificacaoService.criar_notificacao(
                db=db,
                tipo="agendamento",
                titulo=titulo,
                mensagem=mensagem,
                icone=icone,
                cor=cor,
                link=link,
                agendamento_id=agendamento.id,
                data_agendamento=data_iso,
                dados_extra={
                    "cliente_nome": cliente_nome,
                    "barbeiro_nome": barbeiro_nome,
                    "servicos": servicos_nomes,
                    "data": data_str,
                    "hora": hora_str,
                    "acao": acao
                }
            )
        except Exception as e:
            logger.error(f"❌ Erro ao criar notificação de agendamento: {e}")
            return None
    
    @staticmethod
    async def criar_notificacao_lembrete(
        db: AsyncSession,
        agendamento,
        cliente_nome: str,
        tempo: str  # "1h" ou "30min"
    ) -> Notificacao:
        """Cria notificação de lembrete enviado"""
        try:
            icone = "⏰" if tempo == "1h" else "🚨"
            cor = "orange"
            titulo = f"Lembrete {tempo} enviado: {cliente_nome}"
            
            data_str = agendamento.data.strftime("%d/%m/%Y")
            hora_str = agendamento.hora.strftime("%H:%M")
            
            mensagem = f"""
⏰ Lembrete de {tempo} enviado via WhatsApp
👤 Cliente: {cliente_nome}
📅 Agendamento: {data_str} às {hora_str}
            """.strip()
            
            data_iso = agendamento.data.strftime("%Y-%m-%d")
            link = f"/agendamentos?data={data_iso}&destaque={agendamento.id}"
            
            return await NotificacaoService.criar_notificacao(
                db=db,
                tipo="lembrete",
                titulo=titulo,
                mensagem=mensagem,
                icone=icone,
                cor=cor,
                link=link,
                agendamento_id=agendamento.id,
                data_agendamento=data_iso
            )
        except Exception as e:
            logger.error(f"❌ Erro ao criar notificação de lembrete: {e}")
            return None
    
    @staticmethod
    async def criar_notificacao_aniversario(
        db: AsyncSession,
        cliente_nome: str,
        cliente_id: int
    ) -> Notificacao:
        """Cria notificação de aniversário enviado"""
        try:
            return await NotificacaoService.criar_notificacao(
                db=db,
                tipo="aniversario",
                titulo=f"🎂 Aniversário: {cliente_nome}",
                mensagem=f"Parabéns enviado via WhatsApp para {cliente_nome}!",
                icone="🎂",
                cor="purple",
                link=f"/clientes/{cliente_id}/editar"
            )
        except Exception as e:
            logger.error(f"❌ Erro ao criar notificação de aniversário: {e}")
            return None
    
    @staticmethod
    async def listar_notificacoes(
        db: AsyncSession,
        limite: int = 50,
        apenas_nao_lidas: bool = False,
        tipo: str = None
    ) -> list:
        """Lista notificações com filtros"""
        try:
            stmt = select(Notificacao).order_by(Notificacao.criada_em.desc())
            
            if apenas_nao_lidas:
                stmt = stmt.where(Notificacao.lida == False)
            
            if tipo:
                stmt = stmt.where(Notificacao.tipo == tipo)
            
            stmt = stmt.limit(limite)
            
            result = await db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"❌ Erro ao listar notificações: {e}")
            return []
    
    @staticmethod
    async def contar_nao_lidas(db: AsyncSession) -> int:
        """Conta notificações não lidas"""
        try:
            stmt = select(func.count(Notificacao.id)).where(Notificacao.lida == False)
            result = await db.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"❌ Erro ao contar notificações não lidas: {e}")
            return 0
    
    @staticmethod
    async def marcar_como_lida(db: AsyncSession, notificacao_id: int) -> bool:
        """Marca uma notificação como lida"""
        try:
            stmt = (
                update(Notificacao)
                .where(Notificacao.id == notificacao_id)
                .values(lida=True, lida_em=func.now())
            )
            await db.execute(stmt)
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao marcar notificação como lida: {e}")
            await db.rollback()
            return False
    
    @staticmethod
    async def marcar_todas_como_lidas(db: AsyncSession) -> bool:
        """Marca todas as notificações como lidas"""
        try:
            stmt = (
                update(Notificacao)
                .where(Notificacao.lida == False)
                .values(lida=True, lida_em=func.now())
            )
            await db.execute(stmt)
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao marcar todas como lidas: {e}")
            await db.rollback()
            return False
    
    @staticmethod
    async def excluir_notificacao(db: AsyncSession, notificacao_id: int) -> bool:
        """Exclui uma notificação"""
        try:
            stmt = delete(Notificacao).where(Notificacao.id == notificacao_id)
            await db.execute(stmt)
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao excluir notificação: {e}")
            await db.rollback()
            return False
    
    @staticmethod
    async def limpar_notificacoes_antigas(db: AsyncSession, dias: int = 30) -> int:
        """Remove notificações com mais de X dias"""
        try:
            from datetime import timedelta
            data_limite = datetime.now() - timedelta(days=dias)
            
            stmt = delete(Notificacao).where(Notificacao.criada_em < data_limite)
            result = await db.execute(stmt)
            await db.commit()
            
            quantidade = result.rowcount
            logger.info(f"🧹 {quantidade} notificações antigas removidas")
            return quantidade
        except Exception as e:
            logger.error(f"❌ Erro ao limpar notificações antigas: {e}")
            await db.rollback()
            return 0
