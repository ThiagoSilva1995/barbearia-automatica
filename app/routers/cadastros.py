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
from app.utils.formatters import format_name
from app.utils.phone_utils import format_phone_for_storage

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["now"] = datetime.now


# =============================================================================
# CLIENTES
# =============================================================================


@router.get("/cadastrar-cliente", response_class=HTMLResponse)
async def cadastrar_cliente_form(request: Request, db: AsyncSession = Depends(get_db)):
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
            await admin_service.atualizar_cliente(
                db,
                int(cliente_id),
                form_data["nome"],
                form_data["telefone"],
                datetime.strptime(form_data["data_nascimento"], "%Y-%m-%d").date(),
            )
            return RedirectResponse(
                url="/cadastrar-cliente?msg=Cliente+atualizado+com+sucesso",
                status_code=303,
            )
        else:
            await admin_service.criar_cliente(
                db,
                form_data["nome"],
                form_data["telefone"],
                datetime.strptime(form_data["data_nascimento"], "%Y-%m-%d").date(),
            )
            return RedirectResponse(
                url="/cadastrar-cliente?msg=sucesso", status_code=303
            )
    except Exception as e:
        return RedirectResponse(
            url=f"/cadastrar-cliente?erro={str(e)}", status_code=303
        )


@router.get("/lista-clientes", response_class=HTMLResponse)
async def listar_clientes(request: Request, db: AsyncSession = Depends(get_db)):
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
    stmt = select(Cliente).where(Cliente.id == cliente_id)
    result = await db.execute(stmt)
    cliente = result.scalars().first()
    if not cliente:
        return RedirectResponse(
            url="/lista-clientes?erro=Cliente+não+encontrado", status_code=303
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
            url="/cadastrar-cliente?msg=Cliente+atualizado+com+sucesso", status_code=303
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/editar-cliente/{cliente_id}?erro={str(e)}", status_code=303
        )


@router.get("/excluir-cliente/{cliente_id}")
async def excluir_cliente(
    cliente_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        await admin_service.excluir_cliente(db, cliente_id)
        return RedirectResponse(
            url="/cadastrar-cliente?msg=Cliente+excluido+com+sucesso", status_code=303
        )
    except Exception as e:
        if "foreign key" in str(e).lower():
            return RedirectResponse(
                url="/cadastrar-cliente?erro=Cliente+possui+agendamentos+vinculados",
                status_code=303,
            )
        return RedirectResponse(
            url=f"/cadastrar-cliente?erro={str(e)}", status_code=303
        )


# =============================================================================
# SERVIÇOS ✂️ (CORRIGIDO)
# =============================================================================


@router.get("/servicos", response_class=HTMLResponse)
async def listar_servicos(request: Request, db: AsyncSession = Depends(get_db)):
    """Lista todos os serviços cadastrados"""
    # Verifica se é admin
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+restrito", status_code=303)

    result = await db.execute(select(Servico).order_by(Servico.nome))
    return templates.TemplateResponse(
        "administrador/servicos.html",
        {
            "request": request,
            "servicos": result.scalars().all(),
            "msg": request.query_params.get("msg"),
        },
    )


@router.post("/servicos")
async def criar_servico(request: Request, db: AsyncSession = Depends(get_db)):
    """Cria um novo serviço com duração estimada"""
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    form_data = await request.form()
    try:
        nome_formatado = format_name(form_data["nome"])
        preco = Decimal(str(form_data["preco"]).replace(",", "."))

        # ✅ Captura duração minutos (padrão 30 se não enviado)
        duracao_str = form_data.get("duracao_minutos", "30")
        duracao_minutos = int(duracao_str) if duracao_str.isdigit() else 30

        # Verifica duplicidade
        stmt_check = select(Servico).where(Servico.nome.ilike(nome_formatado))
        if (await db.execute(stmt_check)).scalars().first():
            return RedirectResponse(
                url="/servicos?erro=Serviço+já+cadastrado", status_code=303
            )

        # ✅ Salva o serviço com a nova duração
        db.add(
            Servico(nome=nome_formatado, preco=preco, duracao_minutos=duracao_minutos)
        )
        await db.commit()
        return RedirectResponse(url="/servicos?msg=sucesso", status_code=303)
    except Exception as e:
        await db.rollback()
        return RedirectResponse(url=f"/servicos?erro={str(e)}", status_code=303)


@router.get("/excluir-servico/{servico_id}")
async def excluir_servico(
    servico_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Exclui um serviço"""
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    try:
        stmt = select(Servico).where(Servico.id == servico_id)
        res = await db.execute(stmt)
        servico = res.scalars().first()
        if servico:
            await db.delete(servico)
            await db.commit()
            return RedirectResponse(url="/servicos?msg=excluido", status_code=303)
        return RedirectResponse(url="/servicos?erro=Não+encontrado", status_code=303)
    except Exception as e:
        if "foreign key" in str(e).lower():
            return RedirectResponse(
                url="/servicos?erro=Em+uso+em+agendamentos", status_code=303
            )
        return RedirectResponse(url=f"/servicos?erro={str(e)}", status_code=303)


# =============================================================================
# PRODUTOS 🧴
# =============================================================================


@router.get("/produtos", response_class=HTMLResponse)
async def listar_produtos(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+restrito", status_code=303)

    result = await db.execute(select(Produto).order_by(Produto.nome))
    return templates.TemplateResponse(
        "administrador/produtos.html",
        {
            "request": request,
            "produtos": result.scalars().all(),
            "msg": request.query_params.get("msg"),
        },
    )


@router.post("/produtos")
async def criar_produto(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    form_data = await request.form()
    try:
        nome_formatado = format_name(form_data["nome"])
        preco = Decimal(str(form_data["preco"]).replace(",", "."))
        estoque = int(form_data.get("estoque", 0))

        stmt_check = select(Produto).where(Produto.nome.ilike(nome_formatado))
        if (await db.execute(stmt_check)).scalars().first():
            return RedirectResponse(
                url="/produtos?erro=Produto+já+cadastrado", status_code=303
            )

        db.add(Produto(nome=nome_formatado, preco=preco, estoque=estoque))
        await db.commit()
        return RedirectResponse(url="/produtos?msg=sucesso", status_code=303)
    except Exception as e:
        await db.rollback()
        return RedirectResponse(url=f"/produtos?erro={str(e)}", status_code=303)


@router.get("/excluir-produto/{produto_id}")
async def excluir_produto(
    produto_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    try:
        stmt = select(Produto).where(Produto.id == produto_id)
        res = await db.execute(stmt)
        produto = res.scalars().first()
        if produto:
            await db.delete(produto)
            await db.commit()
            return RedirectResponse(url="/produtos?msg=excluido", status_code=303)
        return RedirectResponse(url="/produtos?erro=Não+encontrado", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/produtos?erro={str(e)}", status_code=303)


# =============================================================================
# BARBEIROS ✂️
# =============================================================================


@router.get("/cadastrar-barbeiro", response_class=HTMLResponse)
async def listar_barbeiros(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(
            url="/login?erro=Acesso+restrito+apenas+para+Administradores",
            status_code=303,
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
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    form = await request.form()
    nome = form.get("nome")
    nome_formatado = format_name(nome)
    telefone = "".join(filter(str.isdigit, form.get("telefone", "")))
    id_barbeiro = form.get("id_barbeiro")

    try:
        if id_barbeiro:
            stmt = select(Barbeiro).where(Barbeiro.id == int(id_barbeiro))
            res = await db.execute(stmt)
            barbeiro = res.scalars().first()
            if barbeiro:
                barbeiro.nome = nome_formatado
                barbeiro.telefone = telefone
        else:
            stmt_check = select(Barbeiro).where(Barbeiro.telefone == telefone)
            if (await db.execute(stmt_check)).scalars().first():
                return RedirectResponse(
                    url="/cadastrar-barbeiro?erro=Telefone+já+cadastrado",
                    status_code=303,
                )
            novo_barbeiro = Barbeiro(nome=nome_formatado, telefone=telefone)
            db.add(novo_barbeiro)

        await db.commit()
        return RedirectResponse(
            url="/cadastrar-barbeiro?msg=Barbeiro+salvo+com+sucesso", status_code=303
        )
    except Exception as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/cadastrar-barbeiro?erro={str(e)}", status_code=303
        )


@router.get("/remover-barbeiro/{barbeiro_id}")
async def remover_barbeiro(
    barbeiro_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login?erro=Acesso+negado", status_code=303)

    stmt = select(Barbeiro).where(Barbeiro.id == barbeiro_id)
    res = await db.execute(stmt)
    barbeiro = res.scalars().first()

    if barbeiro:
        await db.delete(barbeiro)
        await db.commit()
        return RedirectResponse(
            url="/cadastrar-barbeiro?msg=Barbeiro+removido", status_code=303
        )

    return RedirectResponse(
        url="/cadastrar-barbeiro?erro=Não+encontrado", status_code=303
    )
