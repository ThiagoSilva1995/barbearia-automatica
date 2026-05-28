from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, time, timedelta, date
import pytz
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete, insert
from app.models.servico import agendamento_servico

from app.services.whatsapp_service import (
    enviar_parabens_aniversariantes,
    gerar_mensagem_aniversario,
    gerar_link_whatsapp,
)

from app.database import get_db
from app.models import Cliente, Barbeiro, Servico, Produto, Agendamento
from app.models.configuracao import Configuracao
from app.schemas.agendamento import AgendamentoCreate
from app.services.agendamento_service import (
    criar_agendamento,
    remover_agendamento,
    confirmar_pagamento_e_baixar_estoque,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


def calcular_horario_fim(hora_inicio: time, duracao_min: int) -> str:
    """Calcula horário de término baseado na duração"""
    if not duracao_min:
        duracao_min = 30

    dt_inicio = datetime.combine(date.today(), hora_inicio)
    dt_fim = dt_inicio + timedelta(minutes=duracao_min)
    return dt_fim.strftime("%H:%M")


def gerar_horarios_disponiveis(
    config: Configuracao,
    data_alvo: date,
    duracao_servico: int = 30,
    buffer_minutos: int = 10,
):
    """
    Gera horários válidos considerando duração do serviço + buffer.
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()

    if dia_semana == 6:  # Domingo
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
        atual = inicio
        tempo_total = duracao_necessaria + buffer_minutos
        while atual + timedelta(minutes=tempo_total) <= fim:
            horarios.append(atual.strftime("%H:%M"))
            atual += timedelta(minutes=tempo_total)

    if inicio_m <= fim_m:
        _adicionar_horarios_dinamicos(inicio_m, fim_m, duracao_servico)
    if inicio_t < fim_t:
        _adicionar_horarios_dinamicos(inicio_t, fim_t, duracao_servico)

    # Filtro para hoje
    if data_alvo == hoje:
        hora_atual_str = agora.strftime("%H:%M")
        horarios = [h for h in horarios if h > hora_atual_str]

    return horarios


@router.get("/agendamentos", response_class=HTMLResponse)
async def listar_agendamentos(request: Request, db: AsyncSession = Depends(get_db)):
    hoje = datetime.now(tz_br).date()
    data_filter_param = request.query_params.get("data")
    barbeiro_filter = request.query_params.get("barbeiro")

    if not data_filter_param:
        data_obj = hoje
        data_filter_str = str(hoje)
    else:
        try:
            data_obj = datetime.strptime(data_filter_param, "%Y-%m-%d").date()
            data_filter_str = data_filter_param
        except ValueError:
            data_obj = hoje
            data_filter_str = str(hoje)

    query = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.data == data_obj)
        .order_by(Agendamento.data, Agendamento.hora)
    )

    if barbeiro_filter:
        try:
            query = query.where(Agendamento.barbeiro_id == int(barbeiro_filter))
        except ValueError:
            pass

    result = await db.execute(query)
    agendamentos = result.scalars().all()

    # ✅ CALCULAR HORÁRIO DE INÍCIO E FIM PARA CADA AGENDAMENTO
    for agd in agendamentos:
        agd.hora_inicio_str = agd.hora.strftime("%H:%M")
        agd.hora_fim_str = calcular_horario_fim(agd.hora, agd.duracao_minutos or 30)
        agd.data_str = agd.data.strftime("%d/%m")

    barbeiros_res = await db.execute(select(Barbeiro).order_by(Barbeiro.nome))

    lista_aniversariantes_com_link = []
    msg_personalizada = None

    if data_obj == hoje:
        stmt_config = select(Configuracao).limit(1)
        res_config = await db.execute(stmt_config)
        config = res_config.scalars().first()
        if config and config.msg_aniversario:
            msg_personalizada = config.msg_aniversario

        clientes_res = await db.execute(select(Cliente))
        todos_clientes = clientes_res.scalars().all()
        aniversariantes_raw = [
            c
            for c in todos_clientes
            if c.data_nascimento.month == hoje.month
            and c.data_nascimento.day == hoje.day
            and not c.parabens_enviado
        ]

        if aniversariantes_raw:
            lista_aniversariantes_com_link = await enviar_parabens_aniversariantes(
                db, aniversariantes_raw, texto_personalizado=msg_personalizada
            )

    return templates.TemplateResponse(
        "agendamentos/agendamentos.html",
        {
            "request": request,
            "agendamentos": agendamentos,
            "barbeiros": barbeiros_res.scalars().all(),
            "aniversariantes_do_dia": lista_aniversariantes_com_link,
            "data_filter": data_filter_str,
            "barbeiro_selecionado": int(barbeiro_filter) if barbeiro_filter else None,
            "eh_hoje": data_obj == hoje,
        },
    )


@router.get("/marcar-horario", response_class=HTMLResponse)
async def marcar_horario_form(request: Request, db: AsyncSession = Depends(get_db)):
    stmt_config = select(Configuracao).limit(1)
    res_config = await db.execute(stmt_config)
    config = res_config.scalars().first()

    if not config:
        config = Configuracao()
        db.add(config)
        await db.commit()
        await db.refresh(config)

    hoje = datetime.now(tz_br).date()

    # ✅ Usa função inteligente (já retorna [] para domingos)
    horarios = gerar_horarios_disponiveis(config, hoje)

    clientes_res = await db.execute(select(Cliente).order_by(Cliente.nome))
    barbeiros_res = await db.execute(select(Barbeiro).order_by(Barbeiro.nome))
    servicos_res = await db.execute(select(Servico).order_by(Servico.nome))

    return templates.TemplateResponse(
        "marcar_horario.html",
        {
            "request": request,
            "horarios_disponiveis": horarios,
            "clientes": clientes_res.scalars().all(),
            "barbeiros": barbeiros_res.scalars().all(),
            "servicos": servicos_res.scalars().all(),
            "data_inicial": hoje.strftime("%Y-%m-%d"),
            "erro": None,
            "msg_domingo": (
                "⛔ A barbearia não funciona aos domingos."
                if hoje.weekday() == 6
                else None
            ),
        },
    )


@router.post("/marcar-horario")
async def marcar_horario_action(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    try:
        servico_ids = [int(x) for x in form_data.getlist("servico")]
        if not servico_ids:
            raise ValueError("Selecione pelo menos um serviço.")

        data_escolhida = datetime.strptime(form_data["data"], "%Y-%m-%d").date()

        # Validação Domingo
        if data_escolhida.weekday() == 6:
            raise ValueError("A barbearia não funciona aos domingos.")

        dados = AgendamentoCreate(
            cliente_id=int(form_data["cliente"]),
            barbeiro_id=int(form_data["barbeiro"]),
            data=data_escolhida,
            hora=datetime.strptime(form_data["hora"], "%H:%M").time(),
            servico_ids=servico_ids,
        )
        await criar_agendamento(db, dados)
        return RedirectResponse(
            url="/agendamentos?msg=sucesso", status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/marcar-horario?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception:
        return RedirectResponse(
            url="/marcar-horario?erro=Erro+interno",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/remover-agendamento/{agendamento_id}")
async def remover_agendamento_route(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    if await remover_agendamento(db, agendamento_id):
        return RedirectResponse(
            url="/agendamentos?msg=removido", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(
        url="/agendamentos?erro=Não+encontrado", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/confirmar-pagamento/{agendamento_id}", response_class=HTMLResponse)
async def confirmar_pagamento_form(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
            selectinload(Agendamento.produtos),
        )
        .where(Agendamento.id == agendamento_id)
    )
    res = await db.execute(stmt)
    agd = res.scalars().first()

    if not agd or agd.pago:
        return RedirectResponse(
            url="/agendamentos?erro=Inválido+ou+Já+pago",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    servicos_res = await db.execute(select(Servico).order_by(Servico.nome))
    produtos_res = await db.execute(
        select(Produto).where(Produto.estoque > 0).order_by(Produto.nome)
    )
    valor_inicial = sum(float(s.preco) for s in agd.servicos)

    return templates.TemplateResponse(
        "agendamentos/confirmar_pagamento.html",
        {
            "request": request,
            "agendamento": agd,
            "servicos": servicos_res.scalars().all(),
            "produtos": produtos_res.scalars().all(),
            "valor_inicial_cortes": f"{valor_inicial:.2f}",
        },
    )


@router.post("/confirmar-pagamento/{agendamento_id}")
async def confirmar_pagamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    try:
        servico_ids = [int(x) for x in form_data.getlist("servico")]
        produtos_qtd = {}
        p_ids = form_data.getlist("produto_id")
        p_qtds = form_data.getlist("quantidade")
        for pid, qtd in zip(p_ids, p_qtds):
            if int(qtd) > 0:
                produtos_qtd[int(pid)] = int(qtd)

        resultado = await confirmar_pagamento_e_baixar_estoque(
            db, agendamento_id, servico_ids, produtos_qtd
        )
        msg = f"Pagamento confirmado! Total: R$ {resultado['total_geral']:.2f}"
        return RedirectResponse(
            url=f"/agendamentos?msg={msg}", status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/confirmar-pagamento/{agendamento_id}?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        print(f"Erro crítico pagamento: {e}")
        return RedirectResponse(
            url=f"/confirmar-pagamento/{agendamento_id}?erro=Erro+interno",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/marcar-parabens-enviado/{cliente_id}")
async def marcar_parabens_enviado(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    res = await db.execute(stmt)
    cliente = res.scalars().first()
    if cliente:
        cliente.parabens_enviado = True
        await db.commit()
    return RedirectResponse(
        url="/agendamentos?msg=Parabéns+enviados!",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/enviar-parabens-whatsapp/{cliente_id}")
async def enviar_parabens_whatsapp(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    res = await db.execute(stmt)
    cliente = res.scalars().first()
    if not cliente:
        return RedirectResponse(
            url="/agendamentos?erro=Cliente+não+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    cliente.parabens_enviado = True
    await db.commit()

    stmt_config = select(Configuracao).limit(1)
    res_config = await db.execute(stmt_config)
    config = res_config.scalars().first()
    msg_text = config.msg_aniversario if config and config.msg_aniversario else None

    msg = gerar_mensagem_aniversario(cliente, texto_personalizado=msg_text)
    link_zap = gerar_link_whatsapp(cliente.telefone, msg)
    return RedirectResponse(url=link_zap, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/editar-agendamento/{agendamento_id}", response_class=HTMLResponse)
async def editar_agendamento_form(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(Agendamento.id == agendamento_id)
    )

    res = await db.execute(stmt)
    agd = res.scalars().first()

    if not agd:
        return RedirectResponse(
            url="/agendamentos?erro=Não+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    stmt_config = select(Configuracao).limit(1)
    res_config = await db.execute(stmt_config)
    config = res_config.scalars().first()

    # ✅ Usa função inteligente
    horarios = gerar_horarios_disponiveis(config, agd.data)

    clientes_res = await db.execute(select(Cliente).order_by(Cliente.nome))
    barbeiros_res = await db.execute(select(Barbeiro).order_by(Barbeiro.nome))
    servicos_res = await db.execute(select(Servico).order_by(Servico.nome))
    servicos_atuais_ids = [s.id for s in agd.servicos]

    return templates.TemplateResponse(
        "agendamentos/editar_agendamento.html",
        {
            "request": request,
            "agendamento": agd,
            "clientes": clientes_res.scalars().all(),
            "barbeiros": barbeiros_res.scalars().all(),
            "servicos": servicos_res.scalars().all(),
            "servicos_atuais_ids": servicos_atuais_ids,
            "horarios_disponiveis": horarios,
            "erro": None,
        },
    )


@router.post("/editar-agendamento/{agendamento_id}")
async def editar_agendamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    try:
        stmt = select(Agendamento).where(Agendamento.id == agendamento_id)
        res = await db.execute(stmt)
        agd = res.scalars().first()
        if not agd:
            raise ValueError("Agendamento não encontrado.")

        nova_data = datetime.strptime(form_data["data"], "%Y-%m-%d").date()

        # Validação Domingo
        if nova_data.weekday() == 6:
            raise ValueError("A barbearia não funciona aos domingos.")

        agd.cliente_id = int(form_data["cliente"])
        agd.barbeiro_id = int(form_data["barbeiro"])
        agd.data = nova_data
        agd.hora = datetime.strptime(form_data["hora"], "%H:%M").time()

        novos_servico_ids = set(int(x) for x in form_data.getlist("servico"))

        stmt_atual = select(agendamento_servico.c.servico_id).where(
            agendamento_servico.c.agendamento_id == agendamento_id
        )
        res_atual = await db.execute(stmt_atual)
        ids_atuais_no_banco = set(row[0] for row in res_atual.fetchall())

        servicos_para_remover = ids_atuais_no_banco - novos_servico_ids
        servicos_para_adicionar = novos_servico_ids - ids_atuais_no_banco

        if servicos_para_remover:
            stmt_delete = delete(agendamento_servico).where(
                agendamento_servico.c.agendamento_id == agendamento_id,
                agendamento_servico.c.servico_id.in_(servicos_para_remover),
            )
            await db.execute(stmt_delete)

        if servicos_para_adicionar:
            for s_id in servicos_para_adicionar:
                await db.execute(
                    insert(agendamento_servico).values(
                        agendamento_id=agendamento_id, servico_id=s_id
                    )
                )

        await db.commit()
        return RedirectResponse(
            url="/agendamentos?msg=Agendamento+atualizado+com+sucesso",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/editar-agendamento/{agendamento_id}?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
