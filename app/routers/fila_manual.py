from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
import pytz
import urllib.parse

from app.database import get_db, AsyncSessionLocal
from app.models import Cliente, Agendamento, Barbeiro
from app.services.whatsapp_service import enviar_mensagem_automatica

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


@router.get("/fila/manual/{horario_vago}", response_class=HTMLResponse)
async def fila_manual_form(
    horario_vago: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """Exibe modal com lista de clientes elegíveis."""
    try:
        horario_vago_dt = datetime.fromisoformat(horario_vago)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de horário inválido")

    # Busca clientes com agendamento futuro no mesmo dia/barbeiro (ajuste a lógica se necessário)
    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.cliente), selectinload(Agendamento.barbeiro))
        .where(
            Agendamento.data == horario_vago_dt.date(),
            Agendamento.hora > horario_vago_dt.time(),
            Agendamento.pago == False,
            Agendamento.is_confirmed == True,
        )
        .order_by(Agendamento.hora)
        .limit(20)
    )

    res = await db.execute(stmt)
    agendamentos_futuros = res.scalars().all()

    clientes_elegiveis = []
    for agd in agendamentos_futuros:
        if agd.cliente and agd.cliente.telefone:
            clientes_elegiveis.append(
                {
                    "cliente_id": agd.cliente.id,
                    "cliente_nome": agd.cliente.nome,
                    "cliente_telefone": agd.cliente.telefone,
                    "agendamento_id": agd.id,
                    "agendamento_hora": agd.hora.strftime("%H:%M"),
                    "barbeiro_nome": agd.barbeiro.nome if agd.barbeiro else "-",
                }
            )

    return templates.TemplateResponse(
        "agendamentos/modal_fila_manual.html",
        {
            "request": request,
            "horario_vago": horario_vago_dt.strftime("%d/%m às %H:%M"),
            "horario_vago_iso": horario_vago_dt.isoformat(),
            "clientes": clientes_elegiveis,
        },
    )


@router.post("/fila/manual/enviar")
async def fila_manual_enviar(request: Request, db: AsyncSession = Depends(get_db)):
    """Processa o envio manual da oferta com LINK de confirmação."""
    form = await request.form()
    horario_vago_iso = form.get("horario_vago")
    cliente_ids = form.getlist("cliente_id")

    if not horario_vago_iso or not cliente_ids:
        return JSONResponse(
            status_code=400,
            content={"erro": "Selecione pelo menos um cliente e horário"},
        )

    try:
        horario_vago_dt = datetime.fromisoformat(horario_vago_iso)
        horario_formatado = horario_vago_dt.strftime("%d/%m às %H:%M")

        # Base URL dinâmica (funciona em localhost e produção)
        base_url = str(request.base_url).rstrip("/")

        enviados = 0
        for cliente_id in cliente_ids:
            stmt_cliente = select(Cliente).where(Cliente.id == int(cliente_id))
            res_cliente = await db.execute(stmt_cliente)
            cliente = res_cliente.scalars().first()

            if not cliente or not cliente.telefone:
                continue

            # 🔗 GERA O LINK DE CONFIRMAÇÃO
            link_params = urllib.parse.urlencode(
                {
                    "cliente_id": cliente.id,
                    "horario": horario_vago_iso,
                    "token": f"{cliente.id}_{int(datetime.now(tz_br).timestamp())}",  # Simples anti-cache
                }
            )
            link_confirmacao = f"{base_url}/fila/manual/confirmar?{link_params}"

            nome_cliente = cliente.nome.split()[0]
            msg = (
                f"⚡ *OPORTUNIDADE RELÂMPAGO!* ⚡\n\n"
                f"Olá, *{nome_cliente}*! 👋\n\n"
                f"Liberou um horário *HOJE às {horario_formatado}* na Barbearia!\n\n"
                f"Quer aproveitar para vir mais cedo?\n\n"
                f"👉 *Clique aqui para confirmar:* {link_confirmacao}\n\n"
                f"Te esperamos! ✂️"
            )

            sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)
            if sucesso:
                enviados += 1

        return JSONResponse(
            status_code=200,
            content={
                "sucesso": True,
                "mensagem": f"✅ Oferta enviada para {enviados} cliente(s)!",
                "enviados": enviados,
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=500, content={"erro": f"Erro ao enviar ofertas: {str(e)}"}
        )


# ==========================================================
# NOVAS ROTAS: PÁGINA E PROCESSAMENTO DE CONFIRMAÇÃO
# ==========================================================


@router.get("/fila/manual/confirmar", response_class=HTMLResponse)
async def fila_confirmar_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Página que o cliente vê ao clicar no link do WhatsApp."""
    cliente_id = request.query_params.get("cliente_id")
    horario_iso = request.query_params.get("horario")

    if not cliente_id or not horario_iso:
        raise HTTPException(status_code=400, detail="Link inválido ou expirado.")

    try:
        novo_horario_dt = datetime.fromisoformat(horario_iso)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de horário inválido.")

    # Busca dados do cliente e agendamento atual
    stmt_cliente = select(Cliente).where(Cliente.id == int(cliente_id))
    res_cliente = await db.execute(stmt_cliente)
    cliente = res_cliente.scalars().first()

    stmt_agd = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro))
        .where(Agendamento.cliente_id == int(cliente_id), Agendamento.pago == False)
    )
    res_agd = await db.execute(stmt_agd)
    agd_atual = res_agd.scalars().first()

    if not cliente or not agd_atual:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado.")

    return templates.TemplateResponse(
        "agendamentos/confirmar_fila.html",
        {
            "request": request,
            "cliente": cliente,
            "agendamento_atual": agd_atual,
            "novo_horario_dt": novo_horario_dt,
            "cliente_id": cliente_id,
            "horario_iso": horario_iso,
        },
    )


@router.post("/fila/manual/confirmar")
async def fila_confirmar_action(request: Request, db: AsyncSession = Depends(get_db)):
    """Processa a confirmação da troca de horário pelo cliente."""
    form = await request.form()
    cliente_id = form.get("cliente_id")
    horario_iso = form.get("horario_iso")
    agendamento_id = form.get("agendamento_id")

    try:
        novo_horario_dt = datetime.fromisoformat(horario_iso)

        # Atualiza o agendamento
        stmt = select(Agendamento).where(Agendamento.id == int(agendamento_id))
        res = await db.execute(stmt)
        agd = res.scalars().first()

        if agd:
            agd.data = novo_horario_dt.date()
            agd.hora = novo_horario_dt.time()
            agd.is_confirmed = True
            agd.pago = False  # Mantém pendente até pagamento

            await db.commit()

            # 🔔 Notifica a barbearia da confirmação
            stmt_cfg = select(Configuracao).limit(1)
            cfg = (await db.execute(stmt_cfg)).scalars().first()
            if cfg and cfg.telefone_barbearia:
                msg_barb = (
                    f"✅ *CLIENTE CONFIRMOU VIA FILA!* ✅\n\n"
                    f"👤 {cliente.nome} aceitou o horário vago.\n"
                    f" Novo horário: {novo_horario_dt.strftime('%d/%m às %H:%M')}\n"
                    f" Agendamento #{agendamento_id} atualizado."
                )
                await enviar_mensagem_automatica(cfg.telefone_barbearia, msg_barb)

            return templates.TemplateResponse(
                "agendamentos/fila_sucesso.html",
                {
                    "request": request,
                    "cliente_nome": cliente.nome,
                    "novo_horario": novo_horario_dt.strftime("%d/%m às %H:%M"),
                },
            )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao confirmar: {str(e)}")
