# app/routers/admin_bloqueios.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, date
import pytz

from app.database import get_db
from app.models.bloqueio import BloqueioHorario

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
tz_br = pytz.timezone("America/Sao_Paulo")


@router.get("/admin/bloqueios", response_class=HTMLResponse)
async def listar_bloqueios(request: Request, db: AsyncSession = Depends(get_db)):
    # CORREÇÃO: Verifica 'is_logged' e se o role é 'admin'
    is_logged = request.session.get("is_logged", False)
    user_role = request.session.get("user_role", "")

    if not is_logged or user_role != "admin":
        return RedirectResponse(url="/login?erro=Acesso+restrito+a+administradores")

    stmt = select(BloqueioHorario).order_by(BloqueioHorario.data)
    res = await db.execute(stmt)
    bloqueios = res.scalars().all()

    return templates.TemplateResponse(
        "admin/bloqueios.html", {"request": request, "bloqueios": bloqueios}
    )


@router.post("/admin/bloqueios/adicionar")
async def adicionar_bloqueio(
    request: Request,
    db: AsyncSession = Depends(get_db),
    data: str = Form(...),
    tipo: str = Form(...),
    inicio_m: str = Form(None),
    fim_m: str = Form(None),
    inicio_t: str = Form(None),
    fim_t: str = Form(None),
    motivo: str = Form(None),
):
    # CORREÇÃO: Verifica 'is_logged' e se o role é 'admin'
    is_logged = request.session.get("is_logged", False)
    user_role = request.session.get("user_role", "")

    if not is_logged or user_role != "admin":
        return RedirectResponse(url="/login?erro=Acesso+restrito+a+administradores")

    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d").date()

        # Converte strings de hora para objetos Time se existirem
        h_im = datetime.strptime(inicio_m, "%H:%M").time() if inicio_m else None
        h_fm = datetime.strptime(fim_m, "%H:%M").time() if fim_m else None
        h_it = datetime.strptime(inicio_t, "%H:%M").time() if inicio_t else None
        h_ft = datetime.strptime(fim_t, "%H:%M").time() if fim_t else None

        novo_bloqueio = BloqueioHorario(
            data=data_obj,
            tipo=tipo,
            horario_inicio_manha=h_im,
            horario_fim_manha=h_fm,
            horario_inicio_tarde=h_it,
            horario_fim_tarde=h_ft,
            motivo=motivo,
        )
        db.add(novo_bloqueio)
        await db.commit()
    except Exception as e:
        print(f"Erro ao adicionar bloqueio: {e}")

    return RedirectResponse(url="/admin/bloqueios?msg=sucesso", status_code=303)


@router.get("/admin/bloqueios/remover/{id}")
async def remover_bloqueio(id: int, request: Request, db: AsyncSession = Depends(get_db)):
    # CORREÇÃO: Verifica 'is_logged' e se o role é 'admin'
    is_logged = request.session.get("is_logged", False)
    user_role = request.session.get("user_role", "")

    if not is_logged or user_role != "admin":
        return RedirectResponse(url="/login?erro=Acesso+restrito+a+administradores")

    stmt = delete(BloqueioHorario).where(BloqueioHorario.id == id)
    await db.execute(stmt)
    await db.commit()

    return RedirectResponse(url="/admin/bloqueios?msg=removido", status_code=303)
