from fastapi import APIRouter, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os

from app.database import get_db
from app.models.configuracao import Configuracao

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/configuracoes", response_class=HTMLResponse)
async def painel_config(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(
            url="/login?erro=Acesso+restrito",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    stmt = select(Configuracao).limit(1)
    res = await db.execute(stmt)
    config = res.scalars().first()

    if not config:
        config = Configuracao()
        db.add(config)
        await db.commit()
        await db.refresh(config)

    return templates.TemplateResponse(
        "admin/configuracoes.html",
        {
            "request": request,
            "config": config,
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
        },
    )


@router.post("/admin/configuracoes/salvar")
async def salvar_config(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()

    stmt = select(Configuracao).limit(1)
    res = await db.execute(stmt)
    config = res.scalars().first()

    # SE NÃO EXISTIR, CRIA UMA NOVA AUTOMATICAMENTE
    if not config:
        config = Configuracao()
        db.add(config)
        await db.flush()

    # Dados Barbearia
    config.nome_fantasia = form.get("nome_fantasia")
    config.telefone_barbearia = "".join(
        filter(str.isdigit, form.get("telefone_barbearia", ""))
    )
    config.endereco = form.get("endereco", "")

    # Horários de Funcionamento
    config.horario_inicio_manha = form.get("horario_inicio_manha")
    config.horario_fim_manha = form.get("horario_fim_manha")
    config.horario_inicio_tarde = form.get("horario_inicio_tarde")
    config.horario_fim_tarde = form.get("horario_fim_tarde")
    config.intervalo_minutos = int(form.get("intervalo_minutos", 30))

    # Mensagens
    config.msg_aniversario = form.get("msg_aniversario")
    config.msg_confirmacao = form.get("msg_confirmacao")

    await db.commit()
    return RedirectResponse(
        url="/admin/configuracoes?msg=Configurações+da+barbearia+atualizadas!",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --- ROTAS DE PERFIL ---


@router.get("/admin/perfil", response_class=HTMLResponse)
async def ver_perfil(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    stmt = select(Configuracao).limit(1)
    res = await db.execute(stmt)
    config = res.scalars().first()

    return templates.TemplateResponse(
        "admin/perfil.html",
        {
            "request": request,
            "config": config,
            "msg": request.query_params.get("msg"),
            "erro": request.query_params.get("erro"),
        },
    )


@router.post("/admin/perfil/salvar")
async def salvar_perfil(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()

    # Busca a configuração existente
    stmt = select(Configuracao).limit(1)
    res = await db.execute(stmt)
    config = res.scalars().first()

    # SE NÃO EXISTIR, CRIA UMA NOVA AUTOMATICAMENTE
    if not config:
        config = Configuracao()
        db.add(config)
        await db.flush()  # Garante que o ID seja gerado antes de continuar

    # Atualiza os campos
    config.admin_nome = form.get("admin_nome")
    config.admin_login = form.get("admin_login")

    await db.commit()
    return RedirectResponse(
        url="/admin/perfil?msg=Dados+do+perfil+atualizados!", status_code=303
    )


@router.post("/admin/perfil/trocar_senha")
async def perfil_trocar_senha(request: Request, db: AsyncSession = Depends(get_db)):
    if request.session.get("user_role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()
    senha_atual = form.get("senha_atual")
    nova_senha = form.get("nova_senha")
    confirmar_senha = form.get("confirmar_senha")

    # Buscar configuração atual no banco
    stmt = select(Configuracao).limit(1)
    res = await db.execute(stmt)
    config = res.scalars().first()

    if not config:
        config = Configuracao()
        db.add(config)
        await db.commit()

    # Usa a senha do banco ou fallback do .env
    senha_correta_db = config.admin_senha or os.getenv("ADMIN_PASSWORD", "admin123")

    if senha_atual != senha_correta_db:
        return RedirectResponse(
            url="/admin/perfil?erro=Senha+atual+incorreta", status_code=303
        )

    if nova_senha != confirmar_senha:
        return RedirectResponse(
            url="/admin/perfil?erro=As+senhas+não+conferem", status_code=303
        )

    # ✅ SALVA A NOVA SENHA NO BANCO
    config.admin_senha = nova_senha
    await db.commit()

    return RedirectResponse(
        url="/admin/perfil?msg=Senha+alterada+com+sucesso!", status_code=303
    )


@router.get("/admin/gestao-completa", response_class=HTMLResponse)
async def admin_gestao_completa(request: Request):
    if (
        not request.session.get("is_logged")
        or request.session.get("user_role") != "admin"
    ):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        "admin/gestao_completa.html", {"request": request}
    )
