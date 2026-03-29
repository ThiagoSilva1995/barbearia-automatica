from fastapi import APIRouter, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, date
import pytz
from app.services.smart_schedule_service import disparar_efeito_dominio

from app.database import get_db
from app.models import Cliente, Barbeiro, Servico, Agendamento
from app.models.configuracao import Configuracao
from app.schemas.agendamento import AgendamentoCreate
from app.services.agendamento_service import (
    criar_agendamento,
    remover_agendamento,
    verificar_disponibilidade,
)
from app.services.whatsapp_service import (
    gerar_mensagem_aniversario,
    gerar_link_whatsapp,
    gerar_mensagem_novo_agendamento,
    gerar_mensagem_alteracao_agendamento,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


@router.get("/cliente", response_class=HTMLResponse)
async def area_cliente_acesso(request: Request):
    return templates.TemplateResponse(
        "cliente/acesso.html",
        {"request": request, "erro": None, "cliente_logado": False},
    )


@router.post("/cliente/acessar")
async def cliente_acessar_action(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    telefone = "".join(filter(str.isdigit, form_data.get("telefone", "")))
    if not telefone:
        return RedirectResponse(
            url="/cliente?erro=Digite+o+telefone", status_code=status.HTTP_303_SEE_OTHER
        )

    stmt = select(Cliente).where(Cliente.telefone.like(f"%{telefone[-9:]}"))
    res = await db.execute(stmt)
    cliente = res.scalars().first()

    if cliente:
        request.session["cliente_id"] = cliente.id
        request.session["cliente_nome"] = cliente.nome
        return RedirectResponse(
            url="/cliente/meus-agendamentos", status_code=status.HTTP_303_SEE_OTHER
        )
    else:
        return RedirectResponse(
            url=f"/cliente/cadastro?telefone={telefone}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/cliente/cadastro", response_class=HTMLResponse)
async def area_cliente_cadastro(request: Request, telefone: str = ""):
    return templates.TemplateResponse(
        "cliente/cadastro.html",
        {
            "request": request,
            "telefone": telefone,
            "erro": None,
            "cliente_logado": False,
        },
    )


@router.post("/cliente/cadastrar")
async def cliente_cadastrar_action(
    request: Request, db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    try:
        nome = form_data.get("nome")
        telefone = "".join(filter(str.isdigit, form_data.get("telefone", "")))
        data_nasc_str = form_data.get("data_nascimento")

        if not nome or not telefone or not data_nasc_str:
            raise ValueError("Preencha todos os campos.")

        data_nasc = datetime.strptime(data_nasc_str, "%Y-%m-%d").date()
        stmt_check = select(Cliente).where(Cliente.telefone.like(f"%{telefone[-9:]}"))
        if (await db.execute(stmt_check)).scalars().first():
            raise ValueError("Telefone já cadastrado!")

        novo_cliente = Cliente(
            nome=nome.title(),
            telefone=telefone,
            data_nascimento=data_nasc,
            parabens_enviado=False,
        )
        db.add(novo_cliente)
        await db.commit()
        await db.refresh(novo_cliente)

        request.session["cliente_id"] = novo_cliente.id
        request.session["cliente_nome"] = novo_cliente.nome
        return RedirectResponse(
            url="/cliente/meus-agendamentos", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/cliente/cadastro?telefone={form_data.get('telefone', '')}&erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/cliente/sair")
async def cliente_sair(request: Request):
    request.session.pop("cliente_id", None)
    request.session.pop("cliente_nome", None)
    return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/cliente/meus-agendamentos", response_class=HTMLResponse)
async def cliente_meus_agendamentos(
    request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")

    # Se não estiver logado, manda para o login/acesso
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    # Busca os dados do cliente
    stmt_cliente = select(Cliente).where(Cliente.id == cliente_id)
    res_cliente = await db.execute(stmt_cliente)
    cliente = res_cliente.scalars().first()

    if not cliente:
        # Se o cliente não existir mais no banco, faz logout
        request.session.pop("cliente_id", None)
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    # Busca todos os agendamentos deste cliente, trazendo Barbeiro e Serviços junto
    stmt_agd = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro), selectinload(Agendamento.servicos))
        .where(Agendamento.cliente_id == cliente_id)
        .order_by(Agendamento.data.desc(), Agendamento.hora.desc())
    )

    res_agd = await db.execute(stmt_agd)
    agendamentos = res_agd.scalars().all()

    # Dados de tempo para comparação (futuro vs passado)
    hoje = datetime.now(tz_br).date()
    hora_atual = datetime.now(tz_br).time()

    return templates.TemplateResponse(
        "cliente/meus_agendamentos.html",
        {
            "request": request,
            "cliente": cliente,
            "agendamentos": agendamentos,
            "hoje": hoje,
            "hora_atual": hora_atual,
            "cliente_logado": True,
        },
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

    horarios_sugeridos = []
    inicio = datetime.strptime("08:00", "%H:%M")
    fim = datetime.strptime("19:00", "%H:%M")
    while inicio <= fim:
        horarios_sugeridos.append(inicio.strftime("%H:%M"))
        inicio += timedelta(minutes=30)

    stmt_ocupados = select(Agendamento.hora, Agendamento.barbeiro_id).where(
        Agendamento.data == data_selecionada
    )
    if barbeiro_id:
        stmt_ocupados = stmt_ocupados.where(Agendamento.barbeiro_id == int(barbeiro_id))

    ocupados = (await db.execute(stmt_ocupados)).all()
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
async def cliente_agendar_confirmar(
    request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    form_data = await request.form()
    try:
        # 1. Capturar dados do formulário
        servico_ids = [int(x) for x in form_data.getlist("servico")]
        hora_str = form_data.get("hora")
        barbeiro_str = form_data.get("barbeiro")
        data_str = form_data.get("data")

        if not servico_ids or not hora_str or not barbeiro_str or not data_str:
            raise ValueError("Preencha todos os campos obrigatórios.")

        # 2. Criar o agendamento no banco
        dados = AgendamentoCreate(
            cliente_id=cliente_id,
            barbeiro_id=int(barbeiro_str),
            data=datetime.strptime(data_str, "%Y-%m-%d").date(),
            hora=datetime.strptime(hora_str, "%H:%M").time(),
            servico_ids=servico_ids,
        )
        await criar_agendamento(db, dados)

        # 3. Buscar dados completos para as mensagens
        stmt_cliente = select(Cliente).where(Cliente.id == cliente_id)
        cliente = (await db.execute(stmt_cliente)).scalars().first()

        stmt_barbeiro = select(Barbeiro).where(Barbeiro.id == int(barbeiro_str))
        barbeiro = (await db.execute(stmt_barbeiro)).scalars().first()

        stmt_servicos = select(Servico).where(Servico.id.in_(servico_ids))
        servicos = (await db.execute(stmt_servicos)).scalars().all()

        # Buscar telefone da barbearia nas configurações
        stmt_config = select(Configuracao).limit(1)
        config = (await db.execute(stmt_config)).scalars().first()
        telefone_barbearia = (
            config.telefone_barbearia if config and config.telefone_barbearia else ""
        )

        # 4. Enviar Mensagens Automáticas (Se houver telefones)
        if telefone_barbearia or (cliente and cliente.telefone):
            nomes_servicos = [s.nome for s in servicos]
            data_formatada = datetime.strptime(data_str, "%Y-%m-%d").strftime(
                "%d/%m/%Y"
            )

            from app.services.whatsapp_service import (
                gerar_mensagem_novo_agendamento,
                gerar_mensagem_confirmacao_cliente,
                enviar_mensagem_automatica,
            )
            import asyncio

            nome_barbeiro = barbeiro.nome if barbeiro else "Equipe"
            nome_cliente_curto = cliente.nome.split()[0]

            # --- A) Mensagem PARA A BARBEARIA ---
            if telefone_barbearia:
                msg_aviso_barbearia = gerar_mensagem_novo_agendamento(
                    cliente_nome=cliente.nome,
                    servicos_nomes=nomes_servicos,
                    data_str=data_formatada,
                    hora_str=hora_str,
                    barbeiro_nome=nome_barbeiro,
                )
                # Dispara em segundo plano
                asyncio.create_task(
                    enviar_mensagem_automatica(telefone_barbearia, msg_aviso_barbearia)
                )

            # --- B) Mensagem PARA O CLIENTE (CONFIRMAÇÃO) ---
            if cliente and cliente.telefone:
                msg_confirmacao_cliente = gerar_mensagem_confirmacao_cliente(
                    cliente_nome=nome_cliente_curto,
                    data_str=data_formatada,
                    hora_str=hora_str,
                    barbeiro_nome=nome_barbeiro,
                    servicos_nomes=nomes_servicos,
                )
                # Dispara em segundo plano
                asyncio.create_task(
                    enviar_mensagem_automatica(
                        cliente.telefone, msg_confirmacao_cliente
                    )
                )

        # 5. Redirecionar para a lista de agendamentos com mensagem de sucesso
        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+realizado!+Confirmação+enviada+no+WhatsApp.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception as e:
        print(f"Erro ao agendar: {e}")
        return RedirectResponse(
            url=f"/cliente/agendar?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )


@router.get("/cliente/editar/{agendamento_id}", response_class=HTMLResponse)
async def cliente_editar_agendamento_form(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    # Busca o agendamento e valida se pertence ao cliente
    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro), selectinload(Agendamento.servicos))
        .where(Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id)
    )
    res = await db.execute(stmt)
    agd = res.scalars().first()

    if not agd:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Agendamento+não+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if agd.pago:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Não+é+possível+editar+agendamentos+já+pagos",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Prepara dados para o formulário
    hoje = datetime.now(tz_br).date()
    barbeiros = (
        (await db.execute(select(Barbeiro).order_by(Barbeiro.nome))).scalars().all()
    )
    servicos = (
        (await db.execute(select(Servico).order_by(Servico.nome))).scalars().all()
    )

    # Gera lista de horários sugeridos (igual na tela de novo agendamento)
    horarios_sugeridos = []
    inicio = datetime.strptime("08:00", "%H:%M")
    fim = datetime.strptime("19:00", "%H:%M")
    while inicio <= fim:
        horarios_sugeridos.append(inicio.strftime("%H:%M"))
        inicio += timedelta(minutes=30)

    # IDs dos serviços atuais para marcar os checkboxes
    servicos_atuais_ids = [s.id for s in agd.servicos]

    # Verifica se há mensagem de erro na URL
    erro_msg = request.query_params.get("erro")

    return templates.TemplateResponse(
        "cliente/editar_agendamento.html",
        {
            "request": request,
            "agendamento": agd,
            "barbeiros": barbeiros,
            "servicos": servicos,
            "horarios_sugeridos": horarios_sugeridos,
            "servicos_atuais_ids": servicos_atuais_ids,
            "hoje": hoje,
            "erro": erro_msg,
            "cliente_logado": True,
        },
    )


@router.post("/cliente/editar/{agendamento_id}")
async def cliente_editar_agendamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    form_data = await request.form()
    try:
        # 1. Buscar agendamento atual
        stmt = (
            select(Agendamento)
            .options(selectinload(Agendamento.servicos))
            .where(
                Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id
            )
        )
        res = await db.execute(stmt)
        agd = res.scalars().first()

        if not agd or agd.pago:
            raise ValueError("Agendamento inválido ou já pago.")

        # Dados novos
        nova_data_str = form_data.get("data")
        nova_hora_str = form_data.get("hora")
        novo_barbeiro_str = form_data.get("barbeiro")
        novos_servico_ids = [int(x) for x in form_data.getlist("servico")]

        if not all(
            [nova_data_str, nova_hora_str, novo_barbeiro_str, novos_servico_ids]
        ):
            raise ValueError("Preencha todos os campos.")

        nova_data = datetime.strptime(nova_data_str, "%Y-%m-%d").date()
        nova_hora = datetime.strptime(nova_hora_str, "%H:%M").time()
        novo_barbeiro_id = int(novo_barbeiro_str)

        # 2. Verificar disponibilidade do NOVO horário
        ocupado = await verificar_disponibilidade(
            db, novo_barbeiro_id, nova_data, nova_hora, exclude_id=agd.id
        )
        if ocupado:
            raise ValueError("Este novo horário já está ocupado!")

        # 3. Salvar dados ANTIGOS para a mensagem
        data_antiga_fmt = agd.data.strftime("%d/%m/%Y")
        hora_antiga_fmt = agd.hora.strftime("%H:%M")

        # 4. Atualizar no Banco
        agd.data = nova_data
        agd.hora = nova_hora
        agd.barbeiro_id = novo_barbeiro_id

        agd.servicos.clear()
        stmt_serv = select(Servico).where(Servico.id.in_(novos_servico_ids))
        res_serv = await db.execute(stmt_serv)
        for s in res_serv.scalars().all():
            agd.servicos.append(s)

        await db.commit()

        # 5. Enviar Aviso Automático
        stmt_config = select(Configuracao).limit(1)
        config = (await db.execute(stmt_config)).scalars().first()
        telefone_barbearia = config.telefone_barbearia if config else ""

        if telefone_barbearia:
            cliente = (
                (await db.execute(select(Cliente).where(Cliente.id == cliente_id)))
                .scalars()
                .first()
            )
            nomes_novos_servicos = [s.nome for s in agd.servicos]
            data_nova_fmt = nova_data.strftime("%d/%m/%Y")

            from app.services.whatsapp_service import (
                gerar_mensagem_alteracao_agendamento,
                enviar_mensagem_automatica,
            )
            import asyncio

            msg_aviso = gerar_mensagem_alteracao_agendamento(
                cliente_nome=cliente.nome,
                data_antiga=data_antiga_fmt,
                hora_antiga=hora_antiga_fmt,
                data_nova=data_nova_fmt,
                hora_nova=nova_hora_str,
                servicos_nomes=nomes_novos_servicos,
            )

            # Dispara o envio em segundo plano (NÃO ABRE NAVEGADOR)
            asyncio.create_task(
                enviar_mensagem_automatica(telefone_barbearia, msg_aviso)
            )

            # Redireciona direto
            return RedirectResponse(
                url="/cliente/meus-agendamentos?msg=Agendamento+alterado!+Aviso+enviado+automaticamente.",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+alterado+com+sucesso!",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception as e:
        print(f"Erro ao editar: {e}")
        return RedirectResponse(
            url=f"/cliente/editar/{agendamento_id}?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/cliente/cancelar/{agendamento_id}")
async def cliente_cancelar_agendamento(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Buscar dados ANTES de cancelar
    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.barbeiro), selectinload(Agendamento.servicos))
        .where(Agendamento.id == agendamento_id, Agendamento.cliente_id == cliente_id)
    )
    res = await db.execute(stmt)
    agd = res.scalars().first()

    if not agd:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Agendamento+não+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if agd.pago:
        return RedirectResponse(
            url="/cliente/meus-agendamentos?erro=Não+é+possível+cancelar+após+pago",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # 2. Preparar dados para mensagem
    stmt_cliente = select(Cliente).where(Cliente.id == cliente_id)
    cliente = (await db.execute(stmt_cliente)).scalars().first()

    nomes_servicos = [s.nome for s in agd.servicos]
    data_fmt = agd.data.strftime("%d/%m/%Y")
    hora_fmt = agd.hora.strftime("%H:%M")
    nome_barbeiro = agd.barbeiro.nome if agd.barbeiro else "Não definido"

    # 3. Buscar telefone da barbearia
    stmt_config = select(Configuracao).limit(1)
    config = (await db.execute(stmt_config)).scalars().first()
    telefone_barbearia = (
        config.telefone_barbearia if config and config.telefone_barbearia else ""
    )

    # 4. Realizar o Cancelamento no Banco
    await remover_agendamento(db, agendamento_id)
    await disparar_efeito_dominio(db, agd.data, agd.hora)

    # 5. Enviar Aviso Automático
    if telefone_barbearia:
        from app.services.whatsapp_service import (
            gerar_mensagem_cancelamento,
            enviar_mensagem_automatica,
        )
        import asyncio

        msg_aviso = gerar_mensagem_cancelamento(
            cliente_nome=cliente.nome,
            data_str=data_fmt,
            hora_str=hora_fmt,
            barbeiro_nome=nome_barbeiro,
            servicos_nomes=nomes_servicos,
        )

        # Dispara o envio em segundo plano (NÃO ABRE NAVEGADOR)
        asyncio.create_task(enviar_mensagem_automatica(telefone_barbearia, msg_aviso))

        # Redireciona direto
        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+cancelado!+Aviso+enviado+automaticamente.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Fallback se não tiver telefone
    return RedirectResponse(
        url="/cliente/meus-agendamentos?msg=Agendamento+cancelado+com+sucesso!",
        status_code=status.HTTP_303_SEE_OTHER,
    )
