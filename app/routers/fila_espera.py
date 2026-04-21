from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import FilaEspera, Agendamento, Cliente
from app.models.configuracao import Configuracao
from app.services.fila_inteligente_service import FilaInteligenteService
from app.services.whatsapp_service import enviar_mensagem_automatica  # ← Adicionado
from datetime import datetime
import os
import logging
import asyncio  # ← Adicionado para background tasks

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@router.get("/fila-espera/confirmar/{fila_id}", response_class=HTMLResponse)
async def pagina_confirmacao_fila(
    fila_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Página de confirmação para o cliente aceitar/recusar horário vago
    Requer autenticação do cliente
    """
    # ← VERIFICAR SE CLIENTE ESTÁ LOGADO
    cliente_id = request.session.get("cliente_id")

    if not cliente_id:
        # ← NÃO LOGADO: Redirecionar para login, salvando URL de retorno
        return RedirectResponse(
            url=f"/cliente?redirect=/fila-espera/confirmar/{fila_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ← BUSCAR FILA COM DADOS DO CLIENTE
    stmt = (
        select(FilaEspera)
        .where(FilaEspera.id == fila_id)
        .options(
            selectinload(FilaEspera.proximo_cliente),
            selectinload(FilaEspera.cliente_atual),
        )
    )

    result = await db.execute(stmt)
    fila = result.scalars().first()

    # ← VERIFICAR SE FILA EXISTE
    if not fila:
        raise HTTPException(status_code=404, detail="Oferta não encontrada")

    # ← VERIFICAR SE É O CLIENTE CORRETO
    if fila.proximo_cliente_id != cliente_id:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Esta+oferta+não+é+para+você",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ← VERIFICAR STATUS DA FILA
    if fila.status != "aguardando":
        return templates.TemplateResponse(
            "fila_espera/ja_respondido.html",
            {
                "request": request,
                "mensagem": "Esta oferta já foi respondida ou expirou.",
            },
        )

    # ← VERIFICAR SE AINDA NÃO EXPIROU (10 minutos)
    if fila.expira_em and fila.expira_em < datetime.now():
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Oferta+expirada",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Formatar dados para exibição
    horario_str = fila.horario_vago.strftime("%H:%M")
    data_str = fila.horario_vago.strftime("%d/%m/%Y")
    nome_cliente = fila.proximo_cliente.nome.split()[0]

    return templates.TemplateResponse(
        "fila_espera/confirmar.html",
        {
            "request": request,
            "fila_id": fila_id,
            "horario": horario_str,
            "data": data_str,
            "nome_cliente": nome_cliente,
            "cliente_id": cliente_id,
            "base_url": BASE_URL,
        },
    )


@router.post("/fila-espera/confirmar/{fila_id}/{acao}")
async def processar_resposta_fila(
    fila_id: int,
    acao: str,  # "aceitar" ou "recusar"
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Processa a resposta do cliente após confirmação na página
    """
    if acao not in ["aceitar", "recusar"]:
        raise HTTPException(status_code=400, detail="Ação inválida")

    # ← VERIFICAR SE CLIENTE ESTÁ LOGADO
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(
            url="/cliente",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ← BUSCAR FILA E VERIFICAR SE É O CLIENTE CORRETO
    stmt = (
        select(FilaEspera)
        .where(
            FilaEspera.id == fila_id,
            FilaEspera.proximo_cliente_id == cliente_id,
            FilaEspera.status == "aguardando",
        )
        .options(selectinload(FilaEspera.proximo_cliente))
    )

    result = await db.execute(stmt)
    fila = result.scalars().first()

    if not fila:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Oferta+inválida+ou+expirada",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ← DEFINIR MENSAGEM PADRÃO (evita UnboundLocalError)
    msg = "Tudo bem! Agradecemos o retorno. 💈"

    fila_service = FilaInteligenteService()
    aceitou = acao == "aceitar"

    if aceitou:
        # ✅ TENTAR ATUALIZAR AGENDAMENTO DO CLIENTE
        # Buscar: cliente + mesma data + horário DIFERENTE do vago (é o agendamento atual dele)
        stmt_agd = select(Agendamento).where(
            Agendamento.cliente_id == cliente_id,
            Agendamento.data == fila.horario_vago.date(),
            Agendamento.hora != fila.horario_vago.time(),  # Exclui o horário vago
        )
        result_agd = await db.execute(stmt_agd)
        agendamento = result_agd.scalars().first()

        logger.info(
            f"🔍 Buscando agendamento: cliente={cliente_id}, data={fila.horario_vago.date()}"
        )
        logger.info(f"🔍 Agendamento encontrado: {agendamento is not None}")

        if agendamento:
            # Salvar horário antigo para a mensagem da barbearia
            horario_antigo_str = agendamento.hora.strftime("%H:%M")

            logger.info(
                f"🔍 Atualizando: {agendamento.hora} → {fila.horario_vago.time()}"
            )
            # Atualizar para o horário vago
            agendamento.hora = fila.horario_vago.time()
            await db.commit()
            logger.info(f"✅ Agendamento {agendamento.id} atualizado!")
            msg = f"✅ Horário confirmado para {fila.horario_vago.strftime('%H:%M')}! Te esperamos! 💈"

            # 🆕 NOTIFICAR A BARBEARIA SOBRE A MUDANÇA
            try:
                # Buscar configuração da barbearia
                stmt_config = select(Configuracao).limit(1)
                config = (await db.execute(stmt_config)).scalars().first()

                if config and config.telefone_barbearia:
                    # Formatar dados para mensagem
                    horario_novo_str = fila.horario_vago.strftime("%H:%M")
                    data_str = fila.horario_vago.strftime("%d/%m/%Y")
                    nome_cliente = fila.proximo_cliente.nome

                    # Mensagem para a barbearia
                    msg_barbearia = (
                        f"🔄 *CLIENTE ALTEROU HORÁRIO VIA FILA* 🔄\n\n"
                        f"👤 *Cliente:* {nome_cliente}\n"
                        f"📅 *Data:* {data_str}\n"
                        f"❌ *Antigo:* {horario_antigo_str}\n"
                        f"✅ *Novo:* {horario_novo_str}\n\n"
                        f"💈 Agenda atualizada automaticamente!"
                    )

                    # Enviar WhatsApp em background (não bloqueia a resposta)
                    asyncio.create_task(
                        enviar_mensagem_automatica(
                            config.telefone_barbearia,
                            msg_barbearia,
                        )
                    )
                    logger.info(
                        f"📤 Notificação enviada para barbearia: {config.telefone_barbearia}"
                    )
            except Exception as e:
                logger.error(f"⚠️ Erro ao notificar barbearia: {e}")
                # Não quebrar o fluxo se notificação falhar

        else:
            # ← FALLBACK: Buscar qualquer agendamento do cliente na data (caso edge)
            logger.warning(
                f"⚠️ Fallback: buscando qualquer agendamento do cliente {cliente_id}"
            )
            stmt_fallback = select(Agendamento).where(
                Agendamento.cliente_id == cliente_id,
                Agendamento.data == fila.horario_vago.date(),
            )
            result_fallback = await db.execute(stmt_fallback)
            agd_fallback = result_fallback.scalars().first()

            if agd_fallback:
                # Salvar horário antigo para notificação
                horario_antigo_str = agd_fallback.hora.strftime("%H:%M")

                agd_fallback.hora = fila.horario_vago.time()
                await db.commit()
                logger.info(f"✅ Fallback: agendamento {agd_fallback.id} atualizado!")
                msg = f"✅ Horário confirmado para {fila.horario_vago.strftime('%H:%M')}! Te esperamos! 💈"

                # 🆕 NOTIFICAR A BARBEARIA (mesma lógica do bloco principal)
                try:
                    stmt_config = select(Configuracao).limit(1)
                    config = (await db.execute(stmt_config)).scalars().first()

                    if config and config.telefone_barbearia:
                        horario_novo_str = fila.horario_vago.strftime("%H:%M")
                        data_str = fila.horario_vago.strftime("%d/%m/%Y")
                        nome_cliente = fila.proximo_cliente.nome

                        msg_barbearia = (
                            f"🔄 *CLIENTE ALTEROU HORÁRIO VIA FILA* 🔄\n\n"
                            f"👤 *Cliente:* {nome_cliente}\n"
                            f"📅 *Data:* {data_str}\n"
                            f"❌ *Antigo:* {horario_antigo_str}\n"
                            f"✅ *Novo:* {horario_novo_str}\n\n"
                            f"💈 Agenda atualizada automaticamente!"
                        )

                        asyncio.create_task(
                            enviar_mensagem_automatica(
                                config.telefone_barbearia,
                                msg_barbearia,
                            )
                        )
                        logger.info(
                            f"📤 Notificação enviada para barbearia: {config.telefone_barbearia}"
                        )
                except Exception as e:
                    logger.error(f"⚠️ Erro ao notificar barbearia: {e}")
            else:
                logger.error(
                    f"❌ Nenhum agendamento encontrado para cliente {cliente_id} na data {fila.horario_vago.date()}"
                )
                # Não atualiza, mas ainda processa a cascata

    # ← Processar cascata SEMPRE (mesmo se não encontrou agendamento)
    await fila_service.processar_resposta(fila_id, aceitou)

    # ← Redirecionar com mensagem (agora sempre definida)
    return RedirectResponse(
        url=f"/cliente/meus-agendamentos?msg={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
