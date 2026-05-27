# app/routers/cliente_publico.py
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

# from app.services.fila_inteligente_service import FilaInteligenteService  # ← COMENTADO
import asyncio

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


def gerar_horarios_disponiveis(
    config: Configuracao,
    data_alvo: date,
    duracao_servico: int = 30,
    buffer_minutos: int = 10,  # Buffer fixo de 10 minutos
):
    """
    Gera horários válidos considerando:
    - Dia da semana (Domingo fechado, Sábado até 12:00)
    - Horário atual (se for hoje)
    - Duração do serviço + buffer: Gera horários dinamicamente
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()

    if dia_semana == 6:  # Domingo: fechado
        return []

    horarios = []
    data_base = hoje

    try:
        inicio_m = datetime.combine(
            data_base,
            datetime.strptime(config.horario_inicio_manha or "08:30", "%H:%M").time(),
        )
        fim_m = datetime.combine(
            data_base,
            datetime.strptime(config.horario_fim_manha or "11:00", "%H:%M").time(),
        )
        inicio_t = datetime.combine(
            data_base,
            datetime.strptime(config.horario_inicio_tarde or "14:00", "%H:%M").time(),
        )
        fim_t = datetime.combine(
            data_base,
            datetime.strptime(config.horario_fim_tarde or "18:30", "%H:%M").time(),
        )
    except Exception:
        inicio_m = datetime.combine(data_base, time(8, 30))
        fim_m = datetime.combine(data_base, time(11, 0))
        inicio_t = datetime.combine(data_base, time(14, 0))
        fim_t = datetime.combine(data_base, time(18, 30))

    # Sábado: fecha às 12:00
    if dia_semana == 5:
        limite_sabado = datetime.combine(data_base, time(12, 0))
        if fim_m > limite_sabado:
            fim_m = limite_sabado
        inicio_t = datetime.combine(data_base, time(23, 0))
        fim_t = datetime.combine(data_base, time(22, 0))

    def _adicionar_horarios_dinamicos(inicio, fim, duracao_necessaria):
        """
        Gera horários dinamicamente baseados na duração do serviço + buffer
        Ex: Se serviço = 45min + buffer 10min = 55min
        Próximo horário = horário anterior + 55min
        """
        atual = inicio
        tempo_total_por_agendamento = duracao_necessaria + buffer_minutos

        while atual + timedelta(minutes=tempo_total_por_agendamento) <= fim:
            horarios.append(atual.strftime("%H:%M"))
            # Avança para o próximo horário baseado na duração + buffer
            atual += timedelta(minutes=tempo_total_por_agendamento)

    if inicio_m <= fim_m:
        _adicionar_horarios_dinamicos(inicio_m, fim_m, duracao_servico)
    if inicio_t < fim_t:
        _adicionar_horarios_dinamicos(inicio_t, fim_t, duracao_servico)

    # Filtro para hoje: remove horários passados
    if data_alvo == hoje:
        hora_atual_str = agora.strftime("%H:%M")
        horarios = [h for h in horarios if h > hora_atual_str]

    return horarios


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
        return RedirectResponse(url="/cliente/agendar", status_code=303)
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
        return RedirectResponse(
            url=f"/cliente?erro=Erro+ao+cadastrar:+{str(e)}", status_code=303
        )


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
        (await db.execute(select(Cliente).where(Cliente.id == cliente_id)))
        .scalars()
        .first()
    )
    barbeiros = (
        (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    )
    servicos = (
        (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()
    )

    stmt_config = select(Configuracao).limit(1)
    config = (await db.execute(stmt_config)).scalars().first()

    # ✅ Calcular duração total + buffer baseada nos serviços selecionados
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

    # ✅ Adicionar buffer de 10 minutos entre agendamentos
    duracao_com_buffer = duracao_total + 10

    # Gera horários considerando duração + buffer
    horarios_sugeridos = gerar_horarios_disponiveis(
        config, data_selecionada, duracao_total
    )

    # Busca agendamentos ocupados COM a duração de cada um
    stmt_ocupados = select(
        Agendamento.hora, Agendamento.duracao_minutos, Agendamento.barbeiro_id
    ).where(Agendamento.data == data_selecionada)
    if barbeiro_id:
        stmt_ocupados = stmt_ocupados.where(Agendamento.barbeiro_id == int(barbeiro_id))

    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()
    horarios_livres = []

    # Verificação de conflito por INTERVALO (com buffer)
    for h_str in horarios_sugeridos:
        h_time = datetime.strptime(h_str, "%H:%M").time()

        # Intervalo do NOVO agendamento (com buffer)
        dt_inicio_novo = datetime.combine(data_selecionada, h_time)
        dt_fim_novo = dt_inicio_novo + timedelta(minutes=duracao_com_buffer)

        esta_livre = True
        for occ_hora, occ_duracao, occ_barb_id in ocupados:
            if not barbeiro_id or int(barbeiro_id) == occ_barb_id:
                # Intervalo do agendamento EXISTENTE (com buffer também)
                occ_dur = (occ_duracao or 30) + 10
                dt_inicio_occ = datetime.combine(data_selecionada, occ_hora)
                dt_fim_occ = dt_inicio_occ + timedelta(minutes=occ_dur)

                # Sobreposição: (InícioA < FimB) e (FimA > InícioB)
                if dt_inicio_novo < dt_fim_occ and dt_fim_novo > dt_inicio_occ:
                    esta_livre = False
                    break

        if esta_livre:
            horarios_livres.append(h_str)

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
        duracao_total = (
            sum(s.duracao_minutos for s in servicos_sel) if servicos_sel else 30
        )

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
async def area_cliente_meus_agendamentos(
    request: Request, db: AsyncSession = Depends(get_db)
):
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
# ROTAS DE EDIÇÃO/CANCELAMENTO (FILA INTELIGENTE DESATIVADA)
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

    barbeiros = (
        (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    )
    servicos = (
        (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()
    )

    # ✅ Calcula duração atual para gerar horários compatíveis
    duracao_atual = agendamento.duracao_minutos or 30
    horarios_sugeridos = gerar_horarios_disponiveis(
        config, agendamento.data, duracao_atual
    )

    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == agendamento.data,
        Agendamento.barbeiro_id == agendamento.barbeiro_id,
        Agendamento.id != agendamento_id,
    )
    ocupados = (await db.execute(stmt_ocupados)).all()

    horarios_livres = []
    for h_str in horarios_sugeridos:
        h_time = datetime.strptime(h_str, "%H:%M").time()
        # Intervalo do NOVO slot
        dt_inicio_novo = datetime.combine(agendamento.data, h_time)
        dt_fim_novo = dt_inicio_novo + timedelta(minutes=duracao_atual)

        esta_livre = True
        for occ_hora, occ_duracao in ocupados:
            occ_dur = occ_duracao or 30
            dt_inicio_occ = datetime.combine(agendamento.data, occ_hora)
            dt_fim_occ = dt_inicio_occ + timedelta(minutes=occ_dur)

            if dt_inicio_novo < dt_fim_occ and dt_fim_novo > dt_inicio_occ:
                esta_livre = False
                break
        if esta_livre:
            horarios_livres.append(h_str)

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
        nova_duracao = (
            sum(s.duracao_minutos for s in servicos_sel) if servicos_sel else 30
        )

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

        # 🔄 FILA INTELIGENTE DESATIVADA - BLOCO COMENTADO
        # fila_service = FilaInteligenteService()
        # asyncio.create_task(
        #     fila_service.criar_cascata_horario_vago(
        #         horario_vago=horario_antigo_datetime,
        #         cliente_que_libertou_id=cliente_id,
        #         horario_novo=datetime.combine(nova_data, nova_hora),
        #     )
        # )

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
                    whatsapp_service.enviar_mensagem_automatica(
                        cfg.telefone_barbearia, msg
                    )
                )

        except Exception as e:
            print(f"⚠️ Erro ao enviar WhatsApp de cancelamento: {e}")

        # 🔄 FILA INTELIGENTE DESATIVADA - BLOCO COMENTADO
        # try:
        #     fila_service = FilaInteligenteService()
        #     asyncio.create_task(
        #         fila_service.criar_cascata_horario_vago(
        #             horario_vago=horario_vago,
        #             cliente_que_libertou_id=cliente_id,
        #         )
        #     )
        # except Exception as e:
        #     print(f"⚠️ Erro ao iniciar fila inteligente: {e}")

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
                await whatsapp_service.enviar_mensagem_automatica(
                    tel_barbearia, msg_barb
                )

            from app.services import whatsapp_service

            msg_cliente = whatsapp_service.gerar_mensagem_confirmacao_cliente(
                agd.cliente.nome.split()[0],
                data_str,
                hora_str,
                agd.barbeiro.nome if agd.barbeiro else "Equipe",
                servicos_nomes,
            )
            await whatsapp_service.enviar_mensagem_automatica(
                agd.cliente.telefone, msg_cliente
            )

    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação de agendamento: {e}")
