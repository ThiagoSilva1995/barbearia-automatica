from fastapi import APIRouter, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, date, time
import pytz
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Cliente, Barbeiro, Servico, Agendamento
from app.models.configuracao import Configuracao
from app.schemas.agendamento import AgendamentoCreate
from app.services.agendamento_service import criar_agendamento

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


def gerar_horarios_disponiveis(config: Configuracao, data_alvo: date):
    """
    Gera horários válidos considerando dia da semana, horário atual e regra de sábado.

    Regras:
    - Domingo: Barbearia fechada (retorna lista vazia)
    - Sábado: Funciona apenas até 12:00 (sem turno da tarde)
    - Seg-Sex: Turnos manhã e tarde conforme configuração
    - Hoje: Remove horários passados automaticamente
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()  # 0=Seg, 5=Sáb, 6=Dom

    # Domingo: Barbearia fechada
    if dia_semana == 6:
        return []

    horarios = []
    intervalo = config.intervalo_minutos if config and config.intervalo_minutos else 30

    # Usa data base consistente para evitar problemas de comparação
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
        # Fallback seguro em caso de erro
        inicio_m = datetime.combine(data_base, time(8, 30))
        fim_m = datetime.combine(data_base, time(11, 0))
        inicio_t = datetime.combine(data_base, time(14, 0))
        fim_t = datetime.combine(data_base, time(18, 30))

    # 📅 Regra de Sábado: Fecha às 12:00
    if dia_semana == 5:  # Sábado
        limite_sabado = datetime.combine(data_base, time(12, 0))

        if fim_m > limite_sabado:
            fim_m = limite_sabado

        # Desativa turno da tarde no sábado
        inicio_t = datetime.combine(data_base, time(23, 0))
        fim_t = datetime.combine(data_base, time(22, 0))

    def _adicionar(inicio, fim):
        """Adiciona horários de inicio até fim com o intervalo configurado"""
        count = 0
        atual = inicio
        while atual <= fim:
            horarios.append(atual.strftime("%H:%M"))
            atual += timedelta(minutes=intervalo)
            count += 1
            if count > 100:  # Segurança para evitar loop infinito
                break

    # Gera horários da manhã
    if inicio_m <= fim_m:
        _adicionar(inicio_m, fim_m)

    # Gera horários da tarde
    if inicio_t < fim_t:
        _adicionar(inicio_t, fim_t)

    # 🕒 Filtro para HOJE: remove horários passados
    if data_alvo == hoje:
        hora_atual_str = agora.strftime("%H:%M")
        horarios = [h for h in horarios if h > hora_atual_str]

    return horarios


@router.get("/cliente", response_class=HTMLResponse)
async def area_cliente_home(request: Request):
    """Redireciona para a página de acesso do cliente."""
    return templates.TemplateResponse("cliente/acesso.html", {"request": request})


@router.post("/cliente/acessar")
async def area_cliente_acessar(request: Request, db: AsyncSession = Depends(get_db)):
    """Verifica se o cliente já existe pelo telefone."""
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
    """Cadastra um novo cliente."""
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
    res_config = await db.execute(stmt_config)
    config = res_config.scalars().first()

    # ✅ Usa a função inteligente que já filtra sábado, domingo e horários passados
    horarios_sugeridos = gerar_horarios_disponiveis(config, data_selecionada)

    stmt_ocupados = select(Agendamento.hora, Agendamento.barbeiro_id).where(
        Agendamento.data == data_selecionada
    )
    if barbeiro_id:
        stmt_ocupados = stmt_ocupados.where(Agendamento.barbeiro_id == int(barbeiro_id))

    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()
    horarios_livres = []

    for h_str in horarios_sugeridos:
        h_time = datetime.strptime(h_str, "%H:%M").time()
        esta_livre = True
        for occ_hora, occ_barb_id in ocupados:
            if occ_hora == h_time and (
                not barbeiro_id or int(barbeiro_id) == occ_barb_id
            ):
                esta_livre = False
                break
        if esta_livre:
            horarios_livres.append(h_str)

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
        dados = AgendamentoCreate(
            cliente_id=cliente_id,
            barbeiro_id=int(form["barbeiro"]),
            data=datetime.strptime(form["data"], "%Y-%m-%d").date(),
            hora=datetime.strptime(form["hora"], "%H:%M").time(),
            servico_ids=servico_ids,
        )
        await criar_agendamento(db, dados)
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

    # Definir data e hora atual para comparação no template
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
# NOVAS ROTAS: EDITAR/CANCELAR AGENDAMENTO (CLIENTE)
# =============================================================================


@router.get("/cliente/editar/{agendamento_id}", response_class=HTMLResponse)
async def cliente_editar_agendamento(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Tela de edição de agendamento para o cliente."""
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    # Buscar agendamento e verificar se pertence ao cliente
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

    # Só permite editar agendamentos futuros e não pagos
    agora = datetime.now(tz_br)
    data_hora_agd = tz_br.localize(datetime.combine(agendamento.data, agendamento.hora))

    if agendamento.pago or data_hora_agd < agora:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Este+agendamento+não+pode+ser+editado",
            status_code=303,
        )

    # Buscar dados para o formulário
    stmt_config = select(Configuracao).limit(1)
    config = (await db.execute(stmt_config)).scalars().first()

    barbeiros = (
        (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    )
    servicos = (
        (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()
    )

    # ✅ Usa função inteligente
    horarios_sugeridos = gerar_horarios_disponiveis(config, agendamento.data)

    # Buscar horários ocupados (exceto o próprio agendamento sendo editado)
    stmt_ocupados = select(Agendamento.hora).where(
        Agendamento.data == agendamento.data,
        Agendamento.barbeiro_id == agendamento.barbeiro_id,
        Agendamento.id != agendamento_id,
    )
    ocupados = (await db.execute(stmt_ocupados)).scalars().all()
    horarios_livres = [
        h
        for h in horarios_sugeridos
        if datetime.strptime(h, "%H:%M").time() not in ocupados
    ]

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
        },
    )


@router.post("/cliente/editar/{agendamento_id}")
async def cliente_editar_agendamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Processa a edição do agendamento pelo cliente."""
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    form = await request.form()

    # Buscar agendamento
    stmt = select(Agendamento).where(
        Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id
    )
    res = await db.execute(stmt)
    agendamento = res.scalars().first()

    if not agendamento:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Agendamento+não+encontrado",
            status_code=303,
        )

    try:
        nova_data = datetime.strptime(form["data"], "%Y-%m-%d").date()
        nova_hora = datetime.strptime(form["hora"], "%H:%M").time()
        novo_barbeiro_id = int(form["barbeiro"])
        novos_servico_ids = [int(x) for x in form.getlist("servico")]

        # Verificar disponibilidade do novo horário
        from app.services.agendamento_service import verificar_disponibilidade

        ocupado = await verificar_disponibilidade(
            db, novo_barbeiro_id, nova_data, nova_hora, exclude_id=agendamento_id
        )
        if ocupado:
            return RedirectResponse(
                url=f"/cliente/editar/{agendamento_id}?erro=Horário+indisponível",
                status_code=303,
            )

        # Atualizar agendamento
        agendamento.data = nova_data
        agendamento.hora = nova_hora
        agendamento.barbeiro_id = novo_barbeiro_id

        # Atualizar serviços
        agendamento.servicos.clear()
        if novos_servico_ids:
            stmt_serv = select(Servico).where(Servico.id.in_(novos_servico_ids))
            res_serv = await db.execute(stmt_serv)
            for s in res_serv.scalars().all():
                agendamento.servicos.append(s)

        await db.commit()

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+atualizado+com+sucesso!",
            status_code=303,
        )

    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/cliente/editar/{agendamento_id}?erro={str(e)}", status_code=303
        )


@router.get("/cliente/cancelar/{agendamento_id}")
async def cliente_cancelar_agendamento(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Cancela um agendamento do cliente."""
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    stmt = select(Agendamento).where(
        Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id
    )
    res = await db.execute(stmt)
    agendamento = res.scalars().first()

    if agendamento and not agendamento.pago:
        await db.delete(agendamento)
        await db.commit()
        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+cancelado+com+sucesso!",
            status_code=303,
        )

    return RedirectResponse(
        url="/cliente/meus-agendamentos?erro=Não+foi+possível+cancelar", status_code=303
    )
