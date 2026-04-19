from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from app.database import get_db
from app.models import Cliente, Barbeiro, Servico, Produto
from app.services import admin_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["now"] = datetime.now


# --- CLIENTES ---
@router.get("/cadastrar-cliente", response_class=HTMLResponse)
async def cadastrar_cliente_form(request: Request, db: AsyncSession = Depends(get_db)):
    """Tela unificada de cadastro e lista de clientes (similar a barbeiros)"""
    result = await db.execute(select(Cliente).order_by(Cliente.id.desc()).limit(10))
    return templates.TemplateResponse(
        "clientes/cadastrar_cliente.html",
        {
            "request": request,
            "erro": request.query_params.get("erro"),
            "msg": request.query_params.get("msg"),
            "clientes_recentes": result.scalars().all(),
        },
    )


@router.post("/cadastrar-cliente")
async def cadastrar_cliente_action(
    request: Request, db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    cliente_id = form_data.get("cliente_id")

    try:
        if cliente_id:
            # Edição de cliente existente
            await admin_service.atualizar_cliente(
                db,
                int(cliente_id),
                form_data["nome"],
                form_data["telefone"],
                datetime.strptime(form_data["data_nascimento"], "%Y-%m-%d").date(),
            )
            return RedirectResponse(
                url="/cadastrar-cliente?msg=Cliente+atualizado+com+sucesso",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        else:
            # Cadastro de novo cliente
            await admin_service.criar_cliente(
                db,
                form_data["nome"],
                form_data["telefone"],
                datetime.strptime(form_data["data_nascimento"], "%Y-%m-%d").date(),
            )
            return RedirectResponse(
                url="/cadastrar-cliente?msg=sucesso",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    except Exception as e:
        if cliente_id:
            return RedirectResponse(
                url=f"/cadastrar-cliente?erro={str(e)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        else:
            return RedirectResponse(
                url=f"/cadastrar-cliente?erro={str(e)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )


@router.get("/lista-clientes", response_class=HTMLResponse)
async def listar_clientes(request: Request, db: AsyncSession = Depends(get_db)):
    """Tela com lista de todos os clientes cadastrados"""
    clientes_com_visitas = await admin_service.get_clientes_com_visitas(db)
    return templates.TemplateResponse(
        "clientes/lista_clientes.html",
        {
            "request": request,
            "clientes": clientes_com_visitas,
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
        },
    )


@router.get("/editar-cliente/{cliente_id}", response_class=HTMLResponse)
async def editar_cliente_form(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Formulário para editar um cliente específico"""
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()

    if not cliente:
        return RedirectResponse(
            url="/lista-clientes?erro=Cliente+não+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        "clientes/editar_cliente.html",
        {
            "request": request,
            "cliente": cliente,
            "erro": request.query_params.get("erro"),
        },
    )


@router.post("/editar-cliente/{cliente_id}")
async def editar_cliente_action(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Ação para salvar edição de cliente"""
    form_data = await request.form()
    try:
        await admin_service.atualizar_cliente(
            db,
            cliente_id,
            form_data["nome"],
            form_data["telefone"],
            datetime.strptime(form_data["data_nascimento"], "%Y-%m-%d").date(),
        )
        return RedirectResponse(
            url="/cadastrar-cliente?msg=Cliente+atualizado+com+sucesso",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/editar-cliente/{cliente_id}?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/excluir-cliente/{cliente_id}")
async def excluir_cliente(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Excluir um cliente"""
    try:
        await admin_service.excluir_cliente(db, cliente_id)
        # ✅ Mude para cadastrar-cliente:
        return RedirectResponse(
            url="/cadastrar-cliente?msg=Cliente+excluido+com+sucesso",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        if "foreign key" in str(e).lower():
            return RedirectResponse(
                url="/cadastrar-cliente?erro=Cliente+possui+agendamentos+vinculados",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/cadastrar-cliente?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# --- SERVIÇOS ---
@router.get("/servicos", response_class=HTMLResponse)
async def listar_servicos(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Servico).order_by(Servico.nome))
    return templates.TemplateResponse(
        "administrador/servicos.html",
        {"request": request, "servicos": result.scalars().all()},
    )


@router.post("/servicos")
async def criar_servico(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    try:
        db.add(
            Servico(
                nome=form_data["nome"],
                preco=Decimal(form_data["preco"].replace(",", ".")),
            )
        )
        await db.commit()
        return RedirectResponse(
            url="/servicos?msg=sucesso", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/servicos?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )


@router.get("/excluir-servico/{servico_id}")
async def excluir_servico(
    servico_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(Servico).where(Servico.id == servico_id)
        res = await db.execute(stmt)
        servico = res.scalars().first()
        if servico:
            await db.delete(servico)
            await db.commit()
            return RedirectResponse(
                url="/servicos?msg=excluido", status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            url="/servicos?erro=Não+encontrado", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        if "foreign key" in str(e).lower():
            return RedirectResponse(
                url="/servicos?erro=Em+uso+em+agendamentos",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/servicos?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )


# --- PRODUTOS ---
@router.get("/produtos", response_class=HTMLResponse)
async def listar_produtos(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Produto).order_by(Produto.nome))
    return templates.TemplateResponse(
        "administrador/produtos.html",
        {"request": request, "produtos": result.scalars().all()},
    )


@router.post("/produtos")
async def criar_produto(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    try:
        db.add(
            Produto(
                nome=form_data["nome"],
                preco=Decimal(form_data["preco"].replace(",", ".")),
                estoque=int(form_data["estoque"]),
            )
        )
        await db.commit()
        return RedirectResponse(
            url="/produtos?msg=sucesso", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/produtos?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )


@router.get("/excluir-produto/{produto_id}")
async def excluir_produto(
    produto_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(Produto).where(Produto.id == produto_id)
        res = await db.execute(stmt)
        produto = res.scalars().first()
        if produto:
            await db.delete(produto)
            await db.commit()
            return RedirectResponse(
                url="/produtos?msg=excluido", status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            url="/produtos?erro=Não+encontrado", status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/produtos?erro={str(e)}", status_code=status.HTTP_303_SEE_OTHER
        )


# ==========================================================
# GERENCIAR BARBEIROS (CORRIGIDO)
# ==========================================================
@router.get("/cadastrar-barbeiro", response_class=HTMLResponse)
async def listar_barbeiros(request: Request, db: AsyncSession = Depends(get_db)):
    # CORREÇÃO: Verifica user_role em vez de is_admin
    if request.session.get("user_role") != "admin":
        return RedirectResponse(
            url="/login?erro=Acesso+restrito+apenas+para+Administradores",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    stmt = select(Barbeiro).order_by(Barbeiro.nome)
    res = await db.execute(stmt)
    barbeiros = res.scalars().all()

    return templates.TemplateResponse(
        "admin/barbeiros.html",
        {
            "request": request,
            "barbeiros": barbeiros,
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
        },
    )


@router.post("/cadastrar-barbeiro/salvar")
async def salvar_barbeiro(request: Request, db: AsyncSession = Depends(get_db)):
    # CORREÇÃO: Verifica user_role
    if request.session.get("user_role") != "admin":
        return RedirectResponse(
            url="/login?erro=Acesso+negado", status_code=status.HTTP_303_SEE_OTHER
        )

    form = await request.form()
    nome = form.get("nome")
    telefone = "".join(filter(str.isdigit, form.get("telefone", "")))
    id_barbeiro = form.get("id_barbeiro")

    try:
        if id_barbeiro:
            stmt = select(Barbeiro).where(Barbeiro.id == int(id_barbeiro))
            res = await db.execute(stmt)
            barbeiro = res.scalars().first()
            if barbeiro:
                barbeiro.nome = nome
                barbeiro.telefone = telefone
        else:
            novo_barbeiro = Barbeiro(nome=nome, telefone=telefone)
            db.add(novo_barbeiro)

        await db.commit()
        return RedirectResponse(
            url="/cadastrar-barbeiro?msg=Barbeiro+salvo+com+sucesso",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/cadastrar-barbeiro?erro={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/remover-barbeiro/{barbeiro_id}")
async def remover_barbeiro(
    barbeiro_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    # CORREÇÃO: Verifica user_role
    if request.session.get("user_role") != "admin":
        return RedirectResponse(
            url="/login?erro=Acesso+negado", status_code=status.HTTP_303_SEE_OTHER
        )

    stmt = select(Barbeiro).where(Barbeiro.id == barbeiro_id)
    res = await db.execute(stmt)
    barbeiro = res.scalars().first()

    if barbeiro:
        await db.delete(barbeiro)
        await db.commit()
        return RedirectResponse(
            url="/cadastrar-barbeiro?msg=Barbeiro+removido",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url="/cadastrar-barbeiro?erro=Não+encontrado",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/lista-completa-clientes", response_class=HTMLResponse)
async def listar_clientes_completo(
    request: Request, db: AsyncSession = Depends(get_db)
):
    """Tela de lista completa com estatísticas de visitas"""
    from sqlalchemy import select, and_
    from app.models import Agendamento

    clientes_result = await db.execute(select(Cliente).order_by(Cliente.nome))
    clientes = clientes_result.scalars().all()

    hoje = datetime.now().date()
    sete_dias_atras = hoje - timedelta(days=7)

    dados_clientes = []
    for cliente in clientes:
        # Visitas na última semana
        stmt_semana = select(Agendamento).where(
            and_(
                Agendamento.cliente_id == cliente.id,
                Agendamento.data >= sete_dias_atras,
                Agendamento.status != "cancelado",
            )
        )
        result_semana = await db.execute(stmt_semana)
        visitas_semana = len(result_semana.scalars().all())

        # Total de visitas
        stmt_total = select(Agendamento).where(
            and_(
                Agendamento.cliente_id == cliente.id, Agendamento.status != "cancelado"
            )
        )
        result_total = await db.execute(stmt_total)
        total_visitas = len(result_total.scalars().all())

        idade = 0
        if cliente.data_nascimento:
            idade = (hoje - cliente.data_nascimento).days // 365

        dados_clientes.append(
            {
                "cliente": cliente,
                "visitas_semana": visitas_semana,
                "total_visitas": total_visitas,
                "idade": idade,
            }
        )

    return templates.TemplateResponse(
        "clientes/lista_completa_clientes.html",
        {"request": request, "dados_clientes": dados_clientes},
    )
