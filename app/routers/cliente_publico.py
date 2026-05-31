from fastapi import APIRouter, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, date, time
import pytz
from sqlalchemy import select, delete, insert
from sqlalchemy.orm import selectinload
from app.database import get_db, AsyncSessionLocal
from app.models import Cliente, Barbeiro, Servico, Agendamento, Configuracao
from app.models.servico import agendamento_servico
from app.schemas.agendamento import AgendamentoCreate
from app.services.agendamento_service import (
    criar_agendamento,
    verificar_disponibilidade,
)

# Importando a nova lógica inteligente
from app.utils.horarios import gerar_slots_disponiveis, filtrar_conflitos

import asyncio

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


@router.get("/cliente", response_class=HTMLResponse)
async def area_cliente_home(request: Request):
    return templates.TemplateResponse("cliente/acesso.html", {"request": request})


@router.post("/cliente/acessar")
async def area_cliente_acessar(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    telefone = "".join(filter(str.isdigit, form.get("telefone", "")))

    if not telefone:
        return RedirectResponse(url="/cliente?erro=Telefone+inválido", status_code=303)

    stmt = select(Cliente).where(Cliente.telefone == telefone)
    res = await db.execute(stmt)
    cliente = res.scalars().first()

    if cliente:
        request.session["cliente_id"] = cliente.id
        request.session["cliente_nome"] = cliente.nome
        return RedirectResponse(url="/cliente/meus-agendamentos", status_code=303)
    else:
        return templates.TemplateResponse(
            "cliente/cadastro.html", {"request": request, "telefone": telefone}
        )


@router.post("/cliente/cadastrar")
async def area_cliente_cadastrar(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    nome = form.get("nome")
    telefone = form.get("telefone")
    data_nasc_str = form.get("data_nascimento")

    try:
        data_nasc = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
        novo_cliente = Cliente(nome=nome, telefone=telefone, data_nascimento=data_nasc)
        db.add(novo_cliente)
        await db.commit()
        await db.refresh(novo_cliente)

        request.session["cliente_id"] = novo_cliente.id
        request.session["cliente_nome"] = novo_cliente.nome
        return RedirectResponse(url="/cliente/agendar", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/cliente?erro=Erro+ao+cadastrar:+{str(e)}", status_code=303)


@router.get("/cliente/agendar", response_class=HTMLResponse)
async def area_cliente_agendar(request: Request, db: AsyncSession = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    hoje = datetime.now(tz_br).date()
    data_str = request.query_params.get("data", str(hoje))
    barbeiro_id = request.query_params.get("barbeiro")

    try:
        data_selecionada = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        data_selecionada = hoje

    cliente_atual = (
        (await db.execute(select(Cliente).where(Cliente.id == cliente_id))).scalars().first()
    )
    barbeiros = (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    servicos = (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()

    stmt_config = select(Configuracao).limit(1)
    config = (await db.execute(stmt_config)).scalars().first()

    # ✅ Calcular duração total baseada nos serviços selecionados
    servico_ids_param = request.query_params.getlist("servico")
    duracao_total = 30
    servicos_selecionados_ids = []

    if servico_ids_param:
        try:
            ids = [int(s) for s in servico_ids_param]
            servicos_selecionados_ids = ids
            stmt_serv = select(Servico).where(Servico.id.in_(ids))
            res_serv = await db.execute(stmt_serv)
            servicos_sel = res_serv.scalars().all()
            if servicos_sel:
                duracao_total = sum(s.duracao_minutos for s in servicos_sel)
        except Exception:
            pass

    # 1. Gera TODOS os slots possíveis (passo de 10min) usando a nova função
    slots_gerados = gerar_slots_disponiveis(config, data_selecionada, passo_minutos=10)

    # 2. Busca ocupações do banco
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == data_selecionada
    )
    if barbeiro_id:
        stmt_ocupados = stmt_ocupados.where(Agendamento.barbeiro_id == int(barbeiro_id))

    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()  # Lista de tuplas (time, int)

    # 3. Filtra conflitos usando a duração real do serviço selecionado
    horarios_livres = filtrar_conflitos(
        slots_gerados, ocupados, duracao_necessaria=duracao_total, buffer=10
    )

    # ✅ Obter horário selecionado (para manter marcado)
    hora_selecionada = request.query_params.get("hora")

    return templates.TemplateResponse(
        "cliente/agendar.html",
        {
            "request": request,
            "cliente": cliente_atual,
            "barbeiros": barbeiros,
            "servicos": servicos,
            "horarios_livres": horarios_livres,
            "data_selecionada": data_selecionada,
            "barbeiro_selecionado": int(barbeiro_id) if barbeiro_id else None,
            "hoje": hoje,
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
            "cliente_logado": True,
            "duracao_total": duracao_total,
            "servicos_selecionados_ids": servicos_selecionados_ids,
            "hora_selecionada": hora_selecionada,
        },
    )


@router.post("/cliente/agendar/confirmar")
async def area_cliente_confirmar(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    try:
        servico_ids = [int(x) for x in form.getlist("servico")]

        # ✅ Calcular duração total dos serviços selecionados para salvar no agendamento
        stmt_serv = select(Servico).where(Servico.id.in_(servico_ids))
        res_serv = await db.execute(stmt_serv)
        servicos_sel = res_serv.scalars().all()
        duracao_total = sum(s.duracao_minutos for s in servicos_sel) if servicos_sel else 30

        dados = AgendamentoCreate(
            cliente_id=cliente_id,
            barbeiro_id=int(form["barbeiro"]),
            data=datetime.strptime(form["data"], "%Y-%m-%d").date(),
            hora=datetime.strptime(form["hora"], "%H:%M").time(),
            servico_ids=servico_ids,
            duracao_minutos=duracao_total,
        )
        novo_agd = await criar_agendamento(db, dados)

        # Disparo do WhatsApp para novo agendamento
        try:
            await asyncio.sleep(0.5)
            await enviar_notificacoes_agendamento(novo_agd.id)
        except Exception as e:
            print(f"⚠️ Erro ao enviar WhatsApp: {e}")

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+realizado!", status_code=303
        )
    except Exception as e:
        return RedirectResponse(url=f"/cliente/agendar?erro={str(e)}", status_code=303)


@router.get("/cliente/meus-agendamentos", response_class=HTMLResponse)
async def area_cliente_meus_agendamentos(request: Request, db: AsyncSession = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro), selectinload(Agendamento.servicos))
        .where(Agendamento.cliente_id == cliente_id)
        .order_by(Agendamento.data.desc(), Agendamento.hora.desc())
    )

    res = await db.execute(stmt)
    agendamentos = res.scalars().all()

    agora = datetime.now(tz_br)
    hoje = agora.date()
    hora_atual = agora.time()

    return templates.TemplateResponse(
        "cliente/meus_agendamentos.html",
        {
            "request": request,
            "agendamentos": agendamentos,
            "msg": request.query_params.get("msg"),
            "hoje": hoje,
            "hora_atual": hora_atual,
        },
    )


# =============================================================================
# ROTAS DE EDIÇÃO/CANCELAMENTO
# =============================================================================


@router.get("/cliente/editar/{agendamento_id}", response_class=HTMLResponse)
async def cliente_editar_agendamento(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro), selectinload(Agendamento.servicos))
        .where(Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id)
    )
    res = await db.execute(stmt)
    agendamento = res.scalars().first()

    if not agendamento:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Agendamento+não+encontrado",
            status_code=303,
        )

    agora = datetime.now(tz_br)
    data_hora_agd = tz_br.localize(datetime.combine(agendamento.data, agendamento.hora))

    if agendamento.pago or data_hora_agd < agora:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Este+agendamento+não+pode+ser+editado",
            status_code=303,
        )

    stmt_config = select(Configuracao).limit(1)
    config = (await db.execute(stmt_config)).scalars().first()

    barbeiros = (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    servicos = (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()

    # ✅ Usa a nova lógica inteligente para edição também
    duracao_atual = agendamento.duracao_minutos or 30

    # 1. Gera slots
    slots_gerados = gerar_slots_disponiveis(config, agendamento.data, passo_minutos=10)

    # 2. Busca ocupados (excluindo o próprio agendamento sendo editado)
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == agendamento.data,
        Agendamento.barbeiro_id == agendamento.barbeiro_id,
        Agendamento.id != agendamento_id,
    )
    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()

    # 3. Filtra
    horarios_livres = filtrar_conflitos(
        slots_gerados, ocupados, duracao_necessaria=duracao_atual, buffer=10
    )

    agora_edit = datetime.now(tz_br)
    hoje_edit = agora_edit.date()
    hora_atual_edit = agora_edit.time()

    return templates.TemplateResponse(
        "cliente/editar_agendamento.html",
        {
            "request": request,
            "agendamento": agendamento,
            "barbeiros": barbeiros,
            "servicos": servicos,
            "horarios_sugeridos": horarios_livres,
            "servicos_atuais_ids": [s.id for s in agendamento.servicos],
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
            "hoje": hoje_edit,
            "hora_atual": hora_atual_edit,
        },
    )


@router.post("/cliente/editar/{agendamento_id}")
async def cliente_editar_agendamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    form = await request.form()

    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id)
    )
    res = await db.execute(stmt)
    agendamento = res.scalars().first()

    if not agendamento:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Agendamento+não+encontrado",
            status_code=303,
        )

    # Salvar dados antigos ANTES de alterar
    data_antiga = agendamento.data.strftime("%d/%m/%Y")
    hora_antiga = agendamento.hora.strftime("%H:%M")
    horario_antigo_datetime = datetime.combine(agendamento.data, agendamento.hora)
    barbeiro_nome = agendamento.barbeiro.nome
    cliente_nome = agendamento.cliente.nome
    servicos_nomes = [s.nome for s in agendamento.servicos]

    try:
        nova_data = datetime.strptime(form["data"], "%Y-%m-%d").date()
        nova_hora = datetime.strptime(form["hora"], "%H:%M").time()
        novo_barbeiro_id = int(form["barbeiro"])
        novos_servico_ids = [int(x) for x in form.getlist("servico")]

        # ✅ Calcular NOVA duração
        stmt_serv = select(Servico).where(Servico.id.in_(novos_servico_ids))
        res_serv = await db.execute(stmt_serv)
        servicos_sel = res_serv.scalars().all()
        nova_duracao = sum(s.duracao_minutos for s in servicos_sel) if servicos_sel else 30

        # Verificar disponibilidade do novo horário com a NOVA duração
        ocupado = await verificar_disponibilidade(
            db,
            novo_barbeiro_id,
            nova_data,
            nova_hora,
            duracao_minutos=nova_duracao,
            exclude_id=agendamento_id,
        )
        if ocupado:
            return RedirectResponse(
                url=f"/cliente/editar/{agendamento_id}?erro=Horário+indisponível",
                status_code=303,
            )

        # Atualizar dados básicos
        agendamento.data = nova_data
        agendamento.hora = nova_hora
        agendamento.barbeiro_id = novo_barbeiro_id
        agendamento.duracao_minutos = nova_duracao

        # Atualizar serviços via SQL direto
        await db.execute(
            delete(agendamento_servico).where(
                agendamento_servico.c.agendamento_id == agendamento_id
            )
        )
        if novos_servico_ids:
            for serv_id in novos_servico_ids:
                await db.execute(
                    insert(agendamento_servico).values(
                        agendamento_id=agendamento_id, servico_id=serv_id
                    )
                )

        await db.commit()

        # 📤 ENVIAR NOTIFICAÇÃO DE ALTERAÇÃO (Background)
        data_nova = nova_data.strftime("%d/%m/%Y")
        hora_nova = nova_hora.strftime("%H:%M")

        from app.services import whatsapp_service

        msg = whatsapp_service.gerar_mensagem_alteracao_agendamento(
            cliente_nome=cliente_nome,
            data_antiga=data_antiga,
            hora_antiga=hora_antiga,
            data_nova=data_nova,
            hora_nova=hora_nova,
            servicos_nomes=servicos_nomes,
        )

        stmt_cfg = select(Configuracao).limit(1)
        cfg = (await db.execute(stmt_cfg)).scalars().first()
        if cfg and cfg.telefone_barbearia:
            asyncio.create_task(
                whatsapp_service.enviar_mensagem_automatica(cfg.telefone_barbearia, msg)
            )

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+atualizado+com+sucesso!",
            status_code=303,
        )

    except Exception as e:
        await db.rollback()
        print(f"ERRO AO EDITAR: {e}")
        return RedirectResponse(
            url=f"/cliente/editar/{agendamento_id}?erro={str(e)}", status_code=303
        )


@router.get("/cliente/cancelar/{agendamento_id}")
async def cliente_cancelar_agendamento(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id)
    )
    res = await db.execute(stmt)
    agendamento = res.scalars().first()

    if agendamento and not agendamento.pago:
        cliente_nome = agendamento.cliente.nome
        data_str = agendamento.data.strftime("%d/%m/%Y")
        hora_str = agendamento.hora.strftime("%H:%M")
        barbeiro_nome = agendamento.barbeiro.nome if agendamento.barbeiro else "Equipe"
        servicos_nomes = [s.nome for s in agendamento.servicos]
        horario_vago = datetime.combine(agendamento.data, agendamento.hora)

        await db.delete(agendamento)
        await db.commit()

        try:
            from app.services import whatsapp_service

            msg = whatsapp_service.gerar_mensagem_cancelamento(
                cliente_nome=cliente_nome,
                data_str=data_str,
                hora_str=hora_str,
                barbeiro_nome=barbeiro_nome,
                servicos_nomes=servicos_nomes,
            )

            stmt_cfg = select(Configuracao).limit(1)
            cfg = (await db.execute(stmt_cfg)).scalars().first()
            if cfg and cfg.telefone_barbearia:
                asyncio.create_task(
                    whatsapp_service.enviar_mensagem_automatica(cfg.telefone_barbearia, msg)
                )

        except Exception as e:
            print(f"⚠️ Erro ao enviar WhatsApp de cancelamento: {e}")

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+cancelado+com+sucesso!",
            status_code=303,
        )

    return RedirectResponse(
        url="/cliente/meus-agendamentos?erro=Não+foi+possível+cancelar",
        status_code=303,
    )


async def enviar_notificacoes_agendamento(agendamento_id: int):
    """Envia confirmações para barbearia e cliente após novo agendamento"""
    try:
        async with AsyncSessionLocal() as db_temp:
            stmt = (
                select(Agendamento)
                .options(
                    selectinload(Agendamento.cliente),
                    selectinload(Agendamento.barbeiro),
                    selectinload(Agendamento.servicos),
                )
                .where(Agendamento.id == agendamento_id)
            )
            res = await db_temp.execute(stmt)
            agd = res.scalars().first()
            if not agd:
                return

            stmt_cfg = select(Configuracao).limit(1)
            cfg = (await db_temp.execute(stmt_cfg)).scalars().first()
            tel_barbearia = cfg.telefone_barbearia if cfg else None

            servicos_nomes = [s.nome for s in agd.servicos]
            data_str = agd.data.strftime("%d/%m/%Y")
            hora_str = agd.hora.strftime("%H:%M")

            if tel_barbearia:
                from app.services import whatsapp_service

                msg_barb = whatsapp_service.gerar_mensagem_novo_agendamento(
                    agd.cliente.nome,
                    servicos_nomes,
                    data_str,
                    hora_str,
                    agd.barbeiro.nome if agd.barbeiro else "Equipe",
                )
                await whatsapp_service.enviar_mensagem_automatica(tel_barbearia, msg_barb)

            from app.services import whatsapp_service

            msg_cliente = whatsapp_service.gerar_mensagem_confirmacao_cliente(
                agd.cliente.nome.split()[0],
                data_str,
                hora_str,
                agd.barbeiro.nome if agd.barbeiro else "Equipe",
                servicos_nomes,
            )
            await whatsapp_service.enviar_mensagem_automatica(agd.cliente.telefone, msg_cliente)

    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação de agendamento: {e}")
