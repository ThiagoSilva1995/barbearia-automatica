from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.notificacao_service import NotificacaoService
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notificacoes", tags=["🔔 Notificações"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def notificacoes_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Página completa de notificações"""
    # Verificar se está logado
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=303)
    
    notificacoes = await NotificacaoService.listar_notificacoes(db, limite=100)
    
    return templates.TemplateResponse(
        "notificacoes.html",
        {
            "request": request,
            "notificacoes": notificacoes,
            "user": request.session.get("user"),
        }
    )


@router.get("/api/notificacoes")
async def api_listar_notificacoes(
    limite: int = 10,
    apenas_nao_lidas: bool = False,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """API: Lista notificações"""
    try:
        notificacoes = await NotificacaoService.listar_notificacoes(
            db, 
            limite=limite, 
            apenas_nao_lidas=apenas_nao_lidas,
            tipo=tipo
        )
        
        return {
            "sucesso": True,
            "notificacoes": [
                {
                    "id": n.id,
                    "tipo": n.tipo,
                    "titulo": n.titulo,
                    "mensagem": n.mensagem,
                    "icone": n.icone,
                    "cor": n.cor,
                    "link": n.link,
                    "agendamento_id": n.agendamento_id,
                    "data_agendamento": n.data_agendamento,
                    "lida": n.lida,
                    "criada_em": n.criada_em.isoformat() if n.criada_em else None,
                    "lida_em": n.lida_em.isoformat() if n.lida_em else None,
                }
                for n in notificacoes
            ]
        }
    except Exception as e:
        logger.error(f"Erro ao listar notificações: {e}")
        return {"sucesso": False, "erro": str(e)}


@router.get("/api/notificacoes/nao-lidas")
async def api_contar_nao_lidas(db: AsyncSession = Depends(get_db)):
    """API: Conta notificações não lidas"""
    try:
        count = await NotificacaoService.contar_nao_lidas(db)
        return {"sucesso": True, "count": count}
    except Exception as e:
        logger.error(f"Erro ao contar notificações não lidas: {e}")
        return {"sucesso": False, "count": 0}


@router.post("/api/notificacoes/{notificacao_id}/ler")
async def api_marcar_como_lida(
    notificacao_id: int,
    db: AsyncSession = Depends(get_db)
):
    """API: Marca uma notificação como lida"""
    try:
        sucesso = await NotificacaoService.marcar_como_lida(db, notificacao_id)
        if sucesso:
            return {"sucesso": True, "mensagem": "Notificação marcada como lida"}
        else:
            raise HTTPException(status_code=400, detail="Erro ao marcar como lida")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao marcar notificação como lida: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/notificacoes/ler-todas")
async def api_marcar_todas_como_lidas(db: AsyncSession = Depends(get_db)):
    """API: Marca todas as notificações como lidas"""
    try:
        sucesso = await NotificacaoService.marcar_todas_como_lidas(db)
        if sucesso:
            return {"sucesso": True, "mensagem": "Todas as notificações marcadas como lidas"}
        else:
            raise HTTPException(status_code=400, detail="Erro ao marcar todas como lidas")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao marcar todas como lidas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/notificacoes/{notificacao_id}")
async def api_excluir_notificacao(
    notificacao_id: int,
    db: AsyncSession = Depends(get_db)
):
    """API: Exclui uma notificação"""
    try:
        sucesso = await NotificacaoService.excluir_notificacao(db, notificacao_id)
        if sucesso:
            return {"sucesso": True, "mensagem": "Notificação excluída"}
        else:
            raise HTTPException(status_code=400, detail="Erro ao excluir notificação")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao excluir notificação: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/notificacoes/limpar-antigas")
async def api_limpar_antigas(
    dias: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """API: Limpa notificações antigas"""
    try:
        quantidade = await NotificacaoService.limpar_notificacoes_antigas(db, dias)
        return {
            "sucesso": True, 
            "mensagem": f"{quantidade} notificações antigas removidas",
            "quantidade": quantidade
        }
    except Exception as e:
        logger.error(f"Erro ao limpar notificações antigas: {e}")
        raise HTTPException(status_code=500, detail=str(e))
