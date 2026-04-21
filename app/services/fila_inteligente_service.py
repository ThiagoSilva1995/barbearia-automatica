from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from app.models import Agendamento, Cliente, FilaEspera
from app.services.whatsapp_service import enviar_mensagem_automatica
from app.database import AsyncSessionLocal
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


class FilaInteligenteService:
    """
    Gerencia o efeito cascata de horários vagos
    """

    TEMPO_RESPOSTA_MINUTOS = 5  # ← 1 minuto para testes (mude para 10 em produção)

    async def criar_cascata_horario_vago(
        self,
        horario_vago: datetime,
        cliente_que_libertou_id: int,
        horario_novo: datetime = None,
    ):
        """
        Inicia o efeito cascata quando um horário fica vago
        """
        async with AsyncSessionLocal() as db:
            try:
                # Buscar todos os agendamentos do mesmo dia, APÓS o horário vago
                stmt = (
                    select(Agendamento)
                    .options(selectinload(Agendamento.cliente))
                    .where(
                        Agendamento.data == horario_vago.date(),
                        Agendamento.hora > horario_vago.time(),
                        Agendamento.cliente_id != cliente_que_libertou_id,
                    )
                    .order_by(Agendamento.hora)
                )

                result = await db.execute(stmt)
                agendamentos = result.scalars().all()

                if not agendamentos:
                    logger.info(f"Sem clientes para oferecer horário {horario_vago}")
                    return None

                # Criar primeira entrada na fila
                primeiro_agendamento = agendamentos[0]

                fila = FilaEspera(
                    horario_vago=horario_vago,
                    cliente_atual_id=cliente_que_libertou_id,
                    proximo_cliente_id=primeiro_agendamento.cliente_id,
                    status="aguardando",
                    expira_em=datetime.now()
                    + timedelta(minutes=self.TEMPO_RESPOSTA_MINUTOS),
                    tentativa=1,
                    horario_novo=horario_novo,
                )

                db.add(fila)
                await db.commit()
                await db.refresh(fila)

                # Enviar mensagem para o primeiro cliente
                await self.enviar_oferta_horario(db, fila.id)

                logger.info(
                    f"Cascata iniciada: horário {horario_vago} oferecido para cliente {primeiro_agendamento.cliente_id}"
                )
                return fila
            except Exception as e:
                logger.error(f"Erro ao criar cascata: {e}")
                await db.rollback()
                raise

    async def enviar_oferta_horario(self, db: AsyncSession, fila_id: int):
        """
        Envia mensagem de oferta de horário para o próximo cliente na fila
        """
        try:
            stmt = (
                select(FilaEspera)
                .options(
                    selectinload(FilaEspera.proximo_cliente),
                    selectinload(FilaEspera.cliente_atual),
                )
                .where(FilaEspera.id == fila_id)
            )

            result = await db.execute(stmt)
            fila = result.scalars().first()

            if not fila or not fila.proximo_cliente:
                logger.error(f"❌ Fila {fila_id} ou cliente não encontrado")
                return

            if fila.status != "aguardando":
                logger.warning(
                    f"⚠️ Fila {fila_id} não está aguardando: status={fila.status}"
                )
                return

            # Formatar horário
            horario_str = fila.horario_vago.strftime("%H:%M")
            data_str = fila.horario_vago.strftime("%d/%m/%Y")

            # Mensagem personalizada
            nome_cliente = fila.proximo_cliente.nome.split()[0]

            mensagem = (
                f"⚡ *OPORTUNIDADE RELÂMPAGO!* ⚡\n\n"
                f"Olá, *{nome_cliente}*! Tudo bem?\n\n"
                f"Liberou um horário às *{horario_str}* hoje ({data_str})!\n\n"
                f"Quer aproveitar para vir mais cedo?\n\n"
                f"⏰ Você tem *{self.TEMPO_RESPOSTA_MINUTOS} minuto(s)* para confirmar.\n"
                f"Basta clicar no link abaixo:\n"
                f"👉 {BASE_URL}/fila-espera/confirmar/{fila.id}\n\n"
                f"Te esperamos! 💈✨"
            )

            # Enviar WhatsApp
            if fila.proximo_cliente.telefone:
                await enviar_mensagem_automatica(
                    fila.proximo_cliente.telefone,
                    mensagem,
                )

                fila.mensagem_enviada = True
                await db.commit()
                logger.info(f"✅ Oferta enviada para cliente {fila.proximo_cliente_id}")
            else:
                logger.warning(
                    f"⚠️ Cliente {fila.proximo_cliente_id} não tem telefone cadastrado"
                )

        except Exception as e:
            logger.error(f"❌ Erro ao enviar oferta: {e}")
            await db.rollback()

    async def processar_resposta(
        self,
        fila_id: int,
        aceitou: bool,
    ):
        """
        Processa a resposta do cliente (aceitou ou recusou)
        """
        async with AsyncSessionLocal() as db:
            try:
                stmt = (
                    select(FilaEspera)
                    .options(
                        selectinload(FilaEspera.proximo_cliente),
                        selectinload(FilaEspera.cliente_atual),
                    )
                    .where(FilaEspera.id == fila_id)
                )

                result = await db.execute(stmt)
                fila = result.scalars().first()

                if not fila:
                    logger.error(f"❌ Fila {fila_id} não encontrada")
                    return

                if aceitou:
                    await self._processar_aceite(db, fila)
                else:
                    await self._processar_recusa(db, fila)
            except Exception as e:
                logger.error(f"❌ Erro ao processar resposta: {e}")
                await db.rollback()

    async def _processar_aceite(self, db: AsyncSession, fila: FilaEspera):
        """
        Processa quando cliente aceita a oferta
        """
        logger.info(
            f"✅ Cliente {fila.proximo_cliente_id} ACEITOU oferta da fila {fila.id}"
        )

        fila.status = "aceita"

        # Buscar próximo cliente na sequência (após o que aceitou)
        stmt = (
            select(Agendamento)
            .options(selectinload(Agendamento.cliente))
            .where(
                Agendamento.data == fila.horario_vago.date(),
                Agendamento.hora > fila.horario_vago.time(),
                Agendamento.cliente_id != fila.proximo_cliente_id,
                Agendamento.cliente_id != fila.cliente_atual_id,
            )
            .order_by(Agendamento.hora)
            .limit(1)
        )

        result = await db.execute(stmt)
        proximo_agd = result.scalars().first()

        if proximo_agd:
            # Criar nova entrada na fila para o próximo cliente
            nova_fila = FilaEspera(
                horario_vago=fila.horario_vago,
                cliente_atual_id=fila.proximo_cliente_id,
                proximo_cliente_id=proximo_agd.cliente_id,
                status="aguardando",
                expira_em=datetime.now()
                + timedelta(minutes=self.TEMPO_RESPOSTA_MINUTOS),
                tentativa=fila.tentativa + 1,
            )

            db.add(nova_fila)
            await db.commit()

            # Enviar mensagem para o próximo
            await self.enviar_oferta_horario(db, nova_fila.id)
            logger.info(
                f"✅ Cascata continua: próximo cliente {proximo_agd.cliente_id}"
            )
        else:
            logger.info(
                f"🔚 Cascata encerrada: sem mais clientes após {fila.proximo_cliente_id}"
            )

    async def _processar_recusa(self, db: AsyncSession, fila: FilaEspera):
        """
        Processa quando cliente recusa ou tempo expira
        ← CORRIGIDO: Mantém histórico de TODOS os clientes já notificados
        """
        logger.info(
            f"🔍 PROCESSANDO RECUSA - Fila {fila.id}, tentativa {fila.tentativa}"
        )

        fila.status = "recusa"

        # ← CORRIGIDO: Buscar TODOS os clientes após o horário vago
        stmt = (
            select(Agendamento)
            .options(selectinload(Agendamento.cliente))
            .where(
                Agendamento.data == fila.horario_vago.date(),
                Agendamento.hora > fila.horario_vago.time(),
                Agendamento.cliente_id != fila.cliente_atual_id,
            )
            .order_by(Agendamento.hora)
        )

        result = await db.execute(stmt)
        todos_agendamentos = result.scalars().all()

        logger.info(
            f"🔍 Total de agendamentos após {fila.horario_vago.time()}: {len(todos_agendamentos)}"
        )

        # ← CORRIGIDO: Filtrar TODOS os clientes já notificados nesta cascata
        # Usamos o campo 'tentativa' para saber quantos clientes já foram pulados
        clientes_ja_notificados = set()

        # Adicionar TODOS os clientes das tentativas anteriores
        # (baseado na ordem dos agendamentos)
        for i, agd in enumerate(todos_agendamentos):
            if (
                i < fila.tentativa
            ):  # ← Clientes das tentativas 0, 1, 2... já foram notificados
                clientes_ja_notificados.add(agd.cliente_id)
                logger.info(
                    f"🔍 Cliente {agd.cliente_id} já notificado na tentativa {i+1}"
                )

        # Buscar PRÓXIMO cliente NÃO notificado
        proximo_agd = None
        for agd in todos_agendamentos:
            if agd.cliente_id not in clientes_ja_notificados:
                proximo_agd = agd
                break

        logger.info(f"🔍 Próximo cliente encontrado: {proximo_agd is not None}")
        if proximo_agd:
            logger.info(
                f"🔍 Cliente ID: {proximo_agd.cliente_id}, Hora: {proximo_agd.hora}"
            )
            if proximo_agd.cliente:
                logger.info(f"🔍 Cliente nome: {proximo_agd.cliente.nome}")

        if proximo_agd:
            # Atualizar fila para próximo cliente
            fila.proximo_cliente_id = proximo_agd.cliente_id
            fila.status = "aguardando"
            fila.expira_em = datetime.now() + timedelta(
                minutes=self.TEMPO_RESPOSTA_MINUTOS
            )
            fila.tentativa += 1

            await db.commit()

            # Enviar mensagem
            await self.enviar_oferta_horario(db, fila.id)
            logger.info(
                f"✅ Cascata continua: tentativa {fila.tentativa}, cliente {proximo_agd.cliente_id}"
            )
        else:
            # ← NÃO HÁ MAIS CLIENTES: encerra a cascata
            fila.status = "expirado"
            await db.commit()
            logger.info(
                f"❌ Cascata encerrada: sem mais clientes para {fila.horario_vago} (total {len(todos_agendamentos)} clientes, {fila.tentativa} tentativas)"
            )

    async def verificar_expiracoes(self):
        """
        Verifica filas expiradas e passa para o próximo cliente
        ← CRIA SUA PRÓPRIA SESSÃO (não recebe db como parâmetro)
        """
        async with AsyncSessionLocal() as db:  # ← Cria sessão interna
            try:
                stmt = select(FilaEspera).where(
                    and_(
                        FilaEspera.status == "aguardando",
                        FilaEspera.expira_em < datetime.now(),
                    )
                )

                result = await db.execute(stmt)
                filas_expiradas = result.scalars().all()

                logger.info(
                    f"🔍 Verificando {len(filas_expiradas)} fila(s) expirada(s)"
                )

                for fila in filas_expiradas:
                    logger.info(f"⏰ Fila {fila.id} expirada, processando recusa")
                    await self._processar_recusa(db, fila)

            except Exception as e:
                logger.error(f"❌ Erro ao verificar expirações: {e}")
                await db.rollback()
