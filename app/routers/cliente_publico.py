from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, time, timedelta
import pytz
from sqlalchemy import select, delete, insert
from sqlalchemy.orm import selectinload
import asyncio

from app.database import get_db, AsyncSessionLocal
from app.models import Cliente, Barbeiro, Servico, Agendamento, Configuracao
from app.models.servico import agendamento_servico
from app.schemas.agendamento import AgendamentoCreate
from app.services.agendamento_service import (
    criar_agendamento,
    verificar_disponibilidade,
)
from app.services.auditoria_service import registrar_auditoria
from app.utils.horarios import gerar_slots_disponiveis, filtrar_conflitos, validar_horario_funcionamento
from app.utils.phone_utils import normalize_phone_for_search
from app.services import whatsapp_service
from app.services.notificacao_service import NotificacaoService

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

    # ✅ CORREÇÃO: Normalizar telefone para busca flexível
    telefone_normalizado = normalize_phone_for_search(telefone)
    
    # Busca flexível: tenta encontrar cliente com telefone que termina com os dígitos informados
    stmt = select(Cliente).where(Cliente.telefone.like(f"%{telefone_normalizado}"))
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

    # ✅ Ordem Alfabética Garantida
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

    # 1. Gera TODOS os slots possíveis (passo de 10min) usando a nova função COM DB
    slots_gerados = await gerar_slots_disponiveis(db, config, data_selecionada, passo_minutos=10)

    # 2. Busca ocupações do banco
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == data_selecionada
    )
    if barbeiro_id:
        stmt_ocupados = stmt_ocupados.where(Agendamento.barbeiro_id == int(barbeiro_id))

    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()  # Lista de tuplas (time, int)

    # 3. Filtra conflitos usando a duração real do serviço selecionado + buffer de 10min
    # ✅ CORREÇÃO: Passa os horários de ambos os períodos (manhã e tarde) para validar corretamente
    # Agora slots no final da manhã que ultrapassam 12:00 são bloqueados (ex: 11:50 + 55min = 12:45)
    
    # Extrair horários de fechamento da config para passar para filtrar_conflitos
    horario_fim_manha = None
    horario_inicio_tarde = None
    horario_fim_tarde = None
    
    if config:
        try:
            if config.horario_fim_manha:
                horario_fim_manha = datetime.strptime(config.horario_fim_manha, "%H:%M").time()
            if config.horario_inicio_tarde:
                horario_inicio_tarde = datetime.strptime(config.horario_inicio_tarde, "%H:%M").time()
            if config.horario_fim_tarde:
                horario_fim_tarde = datetime.strptime(config.horario_fim_tarde, "%H:%M").time()
        except (ValueError, TypeError):
            pass
    
    horarios_livres = filtrar_conflitos(
        slots_gerados, ocupados, 
        duracao_necessaria=duracao_total, 
        buffer=10,
        horario_fim_manha=horario_fim_manha,
        horario_inicio_tarde=horario_inicio_tarde,
        horario_fim_tarde=horario_fim_tarde,
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

        # Chama o serviço que já contém a validação de horário de funcionamento
        novo_agd = await criar_agendamento(db, dados)

        # Disparo do WhatsApp para novo agendamento (Background)
        try:
            await asyncio.sleep(0.5)
            await enviar_notificacoes_agendamento(novo_agd.id)
        except Exception as e:
            print(f"⚠️ Erro ao enviar WhatsApp: {e}")

        # 🔔 Criar notificação in-app para o admin
        try:
            # Buscar dados completos do agendamento
            stmt_completo = (
                select(Agendamento)
                .options(
                    selectinload(Agendamento.cliente),
                    selectinload(Agendamento.barbeiro),
                    selectinload(Agendamento.servicos),
                )
                .where(Agendamento.id == novo_agd.id)
            )
            res_completo = await db.execute(stmt_completo)
            agd_completo = res_completo.scalars().first()
            
            if agd_completo:
                servicos_nomes = [s.nome for s in agd_completo.servicos]
                await NotificacaoService.criar_notificacao_agendamento(
                    db=db,
                    agendamento=agd_completo,
                    cliente_nome=agd_completo.cliente.nome,
                    barbeiro_nome=agd_completo.barbeiro.nome if agd_completo.barbeiro else "Equipe",
                    servicos_nomes=servicos_nomes,
                    acao="criado"
                )
        except Exception as e:
            print(f"⚠️ Erro ao criar notificação in-app: {e}")

        return RedirectResponse(
            url="/cliente/meus-agendamentos?msg=Agendamento+realizado!", status_code=303
        )

    except ValueError as e:
        # Captura erros específicos como "Horário ultrapassa funcionamento"
        print(f"⚠️ [BLOQUEIO DE AGENDAMENTO] Cliente ID: {cliente_id} | Erro: {str(e)}")
        return RedirectResponse(url=f"/cliente/agendar?erro={str(e)}", status_code=303)

    except Exception as e:
        print(f"❌ [ERRO CRÍTICO] Falha ao agendar: {e}")
        return RedirectResponse(
            url="/cliente/agendar?erro=Erro+interno+do+sistema", status_code=303
        )


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

    duracao_atual = agendamento.duracao_minutos or 30

    # 1. Gera slots
    slots_gerados = await gerar_slots_disponiveis(db, config, agendamento.data, passo_minutos=10)

    # 2. Busca ocupados (excluindo o próprio agendamento sendo editado)
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == agendamento.data,
        Agendamento.barbeiro_id == agendamento.barbeiro_id,
        Agendamento.id != agendamento_id,
    )
    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()

    # 3. Filtra
    # ✅ CORREÇÃO: Passa os horários de ambos os períodos (manhã e tarde) para validar corretamente
    # Agora slots no final da manhã que ultrapassam 12:00 são bloqueados (ex: 11:50 + 55min = 12:45)
    
    # Extrair horários de fechamento da config para passar para filtrar_conflitos
    horario_fim_manha = None
    horario_inicio_tarde = None
    horario_fim_tarde = None
    
    if config:
        try:
            if config.horario_fim_manha:
                horario_fim_manha = datetime.strptime(config.horario_fim_manha, "%H:%M").time()
            if config.horario_inicio_tarde:
                horario_inicio_tarde = datetime.strptime(config.horario_inicio_tarde, "%H:%M").time()
            if config.horario_fim_tarde:
                horario_fim_tarde = datetime.strptime(config.horario_fim_tarde, "%H:%M").time()
        except (ValueError, TypeError):
            pass
    
    horarios_livres = filtrar_conflitos(
        slots_gerados, ocupados, 
        duracao_necessaria=duracao_atual, 
        buffer=10,
        horario_fim_manha=horario_fim_manha,
        horario_inicio_tarde=horario_inicio_tarde,
        horario_fim_tarde=horario_fim_tarde,
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


# app/routers/cliente_publico.py


@router.post("/cliente/editar/{agendamento_id}")
async def cliente_editar_agendamento_action(
    agendamento_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse(url="/cliente", status_code=303)

    form = await request.form()

    # Buscar agendamento original
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

    # Salvar dados antigos para notificação
    data_antiga = agendamento.data.strftime("%d/%m/%Y")
    hora_antiga = agendamento.hora.strftime("%H:%M")
    barbeiro_nome = agendamento.barbeiro.nome
    cliente_nome = agendamento.cliente.nome
    servicos_nomes_antigos = [s.nome for s in agendamento.servicos]

    try:
        nova_data = datetime.strptime(form["data"], "%Y-%m-%d").date()
        nova_hora = datetime.strptime(form["hora"], "%H:%M").time()
        novo_barbeiro_id = int(form["barbeiro"])
        novos_servico_ids = [int(x) for x in form.getlist("servico")]

        # ✅ 1. Calcular NOVA duração total
        stmt_serv = select(Servico).where(Servico.id.in_(novos_servico_ids))
        res_serv = await db.execute(stmt_serv)
        servicos_sel = res_serv.scalars().all()
        nova_duracao = sum(s.duracao_minutos for s in servicos_sel) if servicos_sel else 30

        # ✅ 2. Verificar Disponibilidade (Conflito com outros clientes)
        # Usamos a função verificar_disponibilidade que já checa sobreposição baseada na duração
        # ✅ CORREÇÃO: Passa buffer=10 para validar conflitos com margem de limpeza
        ocupado = await verificar_disponibilidade(
            db,
            novo_barbeiro_id,
            nova_data,
            nova_hora,
            duracao_minutos=nova_duracao,
            exclude_id=agendamento_id,  # Exclui o próprio agendamento da verificação
            buffer=10,  # ✅ Buffer de 10min entre agendamentos
        )

        if ocupado:
            return RedirectResponse(
                url=f"/cliente/editar/{agendamento_id}?erro=Horário+indisponível+para+a+nova+duração+selecionada.",
                status_code=303,
            )

        # ✅ 3. Verificar Horário de Funcionamento (Ex: Sábado até 12h)
        from app.models.configuracao import Configuracao

        stmt_config = select(Configuracao).limit(1)
        res_config = await db.execute(stmt_config)
        config = res_config.scalars().first()

        if config:
            # ✅ Usa a função utilitária que valida corretamente os dois períodos (manhã/tarde)
            await validar_horario_funcionamento(
                data=nova_data,
                hora_inicio=nova_hora,
                duracao_minutos=nova_duracao,
                config=config,
                tolerancia_minutos=5,
            )

        # --- Se passou pelas validações, atualiza o banco ---

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

        # 🔔 Criar notificação in-app de alteração
        try:
            # Recarregar agendamento com dados atualizados
            stmt_atualizado = (
                select(Agendamento)
                .options(
                    selectinload(Agendamento.cliente),
                    selectinload(Agendamento.barbeiro),
                    selectinload(Agendamento.servicos),
                )
                .where(Agendamento.id == agendamento_id)
            )
            res_atualizado = await db.execute(stmt_atualizado)
            agd_atualizado = res_atualizado.scalars().first()
            
            if agd_atualizado:
                novos_servicos_nomes = [s.nome for s in agd_atualizado.servicos]
                await NotificacaoService.criar_notificacao_agendamento(
                    db=db,
                    agendamento=agd_atualizado,
                    cliente_nome=agd_atualizado.cliente.nome,
                    barbeiro_nome=agd_atualizado.barbeiro.nome if agd_atualizado.barbeiro else "Equipe",
                    servicos_nomes=novos_servicos_nomes,
                    acao="alterado"
                )
        except Exception as e:
            print(f"⚠️ Erro ao criar notificação de alteração: {e}")

        # 📤 ENVIAR NOTIFICAÇÃO DE ALTERAÇÃO POR WHATSAPP
        # ✅ CORREÇÃO: Dispara para barbearia E cliente (como faz no novo agendamento)
        try:
            await enviar_notificacoes_alteracao(
                agendamento_id=agendamento_id,
                data_antiga=data_antiga,
                hora_antiga=hora_antiga,
            )
        except Exception as e:
            print(f"⚠️ Erro ao enviar WhatsApp de alteração: {e}")

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
        data_iso = agendamento.data.strftime("%Y-%m-%d")
        agendamento_id_para_notificacao = agendamento.id

        # 🔔 Criar notificação in-app de cancelamento ANTES de deletar o agendamento
        try:
            await NotificacaoService.criar_notificacao(
                db=db,
                tipo="agendamento",
                titulo=f"❌ Agendamento Cancelado: {cliente_nome}",
                mensagem=f"""
❌ Agendamento cancelado pelo cliente
👤 Cliente: {cliente_nome}
💇 Barbeiro: {barbeiro_nome}
📅 Data: {data_str} às {hora_str}
✂️ Serviços: {', '.join(servicos_nomes)}
                """.strip(),
                icone="❌",
                cor="red",
                link=f"/agendamentos?data={data_iso}",
                agendamento_id=agendamento_id_para_notificacao,
                data_agendamento=data_iso,
                dados_extra={
                    "cliente_nome": cliente_nome,
                    "barbeiro_nome": barbeiro_nome,
                    "servicos": servicos_nomes,
                    "data": data_str,
                    "hora": hora_str,
                    "acao": "cancelado"
                }
            )
        except Exception as e:
            print(f"⚠️ Erro ao criar notificação de cancelamento: {e}")

        # Agora sim, deletar o agendamento
        await db.delete(agendamento)
        await db.commit()
        
        # 🔍 Registrar auditoria de cancelamento pelo cliente
        try:
            await registrar_auditoria(
                db=db,
                acao="cancelado_cliente",
                agendamento=agendamento,
                usuario_tipo="cliente",
                usuario_id=cliente_id,
                usuario_nome=cliente_nome,
                ip_origem=request.client.host if request.client else None
            )
        except Exception as e:
            print(f"⚠️ Erro ao registrar auditoria de cancelamento: {e}")

        # 📤 ENVIAR NOTIFICAÇÕES DE CANCELAMENTO POR WHATSAPP
        # ✅ CORREÇÃO: Dispara para barbearia E cliente (como faz no novo agendamento e edição)
        try:
            await enviar_notificacoes_cancelamento(
                cliente_nome=cliente_nome,
                cliente_telefone=None,  # Busca da sessão temporária
                data_str=data_str,
                hora_str=hora_str,
                barbeiro_nome=barbeiro_nome,
                servicos_nomes=servicos_nomes,
                cliente_id=cliente_id,
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
                msg_barb = whatsapp_service.gerar_mensagem_novo_agendamento(
                    agd.cliente.nome,
                    servicos_nomes,
                    data_str,
                    hora_str,
                    agd.barbeiro.nome if agd.barbeiro else "Equipe",
                )
                await whatsapp_service.enviar_mensagem_automatica(tel_barbearia, msg_barb)

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


async def enviar_notificacoes_alteracao(
    agendamento_id: int,
    data_antiga: str,
    hora_antiga: str,
):
    """Envia notificação de alteração para barbearia e cliente usando sessão própria."""
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
                print("⚠️ Agendamento não encontrado para envio de notificação de alteração")
                return

            stmt_cfg = select(Configuracao).limit(1)
            cfg = (await db_temp.execute(stmt_cfg)).scalars().first()
            tel_barbearia = cfg.telefone_barbearia if cfg else None

            # Dados ATUALIZADOS do agendamento
            servicos_nomes_novos = [s.nome for s in agd.servicos]
            data_nova_str = agd.data.strftime("%d/%m/%Y")
            hora_nova_str = agd.hora.strftime("%H:%M")
            cliente_nome = agd.cliente.nome
            barbeiro_nome = agd.barbeiro.nome if agd.barbeiro else "Equipe"
            cliente_telefone = agd.cliente.telefone

            # 1. Enviar para a BARBEARIA (avisando que o cliente alterou)
            if tel_barbearia:
                msg_barb = whatsapp_service.gerar_mensagem_alteracao_agendamento(
                    cliente_nome=cliente_nome,
                    data_antiga=data_antiga,
                    hora_antiga=hora_antiga,
                    data_nova=data_nova_str,
                    hora_nova=hora_nova_str,
                    servicos_nomes=servicos_nomes_novos,
                )
                await whatsapp_service.enviar_mensagem_automatica(tel_barbearia, msg_barb)

            # 2. Enviar para o CLIENTE (confirmando a alteração dele)
            if cliente_telefone:
                primeiro_nome = cliente_nome.split()[0]
                servicos_str = ", ".join(servicos_nomes_novos)
                msg_cliente = (
                    f"🔄 *SEU AGENDAMENTO FOI ALTERADO!* 🔄\n\n"
                    f"Olá, *{primeiro_nome}*! Seu horário foi atualizado com sucesso.\n\n"
                    f"✂️ *Serviços:* {servicos_str}\n"
                    f"📅 *Nova Data:* {data_nova_str}\n"
                    f"⏰ *Novo Horário:* {hora_nova_str}\n"
                    f"💇 *Barbeiro:* {barbeiro_nome}\n\n"
                    f"Chegue com 5 minutos de antecedência. Qualquer imprevisto, nos avise!\n"
                    f"Te esperamos! 💈✨"
                )
                await whatsapp_service.enviar_mensagem_automatica(cliente_telefone, msg_cliente)

    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação de alteração: {e}")


async def enviar_notificacoes_cancelamento(
    cliente_nome: str,
    cliente_telefone: str,
    data_str: str,
    hora_str: str,
    barbeiro_nome: str,
    servicos_nomes: list,
    cliente_id: int,
):
    """Envia notificação de cancelamento para barbearia e cliente usando sessão própria."""
    try:
        async with AsyncSessionLocal() as db_temp:
            # Buscar telefone do cliente se não foi passado
            if not cliente_telefone:
                stmt_cliente = select(Cliente).where(Cliente.id == cliente_id)
                res_cliente = await db_temp.execute(stmt_cliente)
                cliente = res_cliente.scalars().first()
                cliente_telefone = cliente.telefone if cliente else None

            stmt_cfg = select(Configuracao).limit(1)
            cfg = (await db_temp.execute(stmt_cfg)).scalars().first()
            tel_barbearia = cfg.telefone_barbearia if cfg else None

            # 1. Enviar para a BARBEARIA (avisando que o cliente cancelou)
            if tel_barbearia:
                msg_barb = whatsapp_service.gerar_mensagem_cancelamento(
                    cliente_nome=cliente_nome,
                    data_str=data_str,
                    hora_str=hora_str,
                    barbeiro_nome=barbeiro_nome,
                    servicos_nomes=servicos_nomes,
                )
                await whatsapp_service.enviar_mensagem_automatica(tel_barbearia, msg_barb)

            # 2. Enviar para o CLIENTE (confirmando que ele cancelou)
            if cliente_telefone:
                primeiro_nome = cliente_nome.split()[0]
                servicos_str = ", ".join(servicos_nomes)
                msg_cliente = (
                    f"❌ *AGENDAMENTO CANCELADO* ❌\n\n"
                    f"Olá, *{primeiro_nome}*! Seu agendamento foi cancelado com sucesso.\n\n"
                    f"✂️ *Serviços:* {servicos_str}\n"
                    f"📅 *Data:* {data_str}\n"
                    f"⏰ *Horário:* {hora_str}\n"
                    f"💇 *Barbeiro:* {barbeiro_nome}\n\n"
                    f"Esperamos te ver em breve! 💈✨\n"
                    f"Se precisar remarcar, é só acessar nosso sistema novamente."
                )
                await whatsapp_service.enviar_mensagem_automatica(cliente_telefone, msg_cliente)

    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação de cancelamento: {e}")


@router.get("/cliente/sair")
async def cliente_logout(request: Request):
    request.session.pop("cliente_id", None)
    request.session.pop("cliente_nome", None)
    return RedirectResponse(url="/cliente", status_code=303)
