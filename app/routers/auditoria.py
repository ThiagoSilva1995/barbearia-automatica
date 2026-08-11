from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auditoria_service import buscar_auditoria
from datetime import datetime, timedelta
import pytz
from pathlib import Path

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])
tz_br = pytz.timezone("America/Sao_Paulo")


def check_admin_session(request: Request):
    """Verifica se o usuário está logado como admin ou super_admin"""
    is_logged = request.session.get("is_logged", False)
    user_role = request.session.get("user_role", "")
    
    if not is_logged or user_role not in ["admin", "super_admin"]:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return True


@router.get("", response_class=HTMLResponse)
async def pagina_auditoria(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin_session),
    dias: int = Query(default=7, ge=1, le=90),
    acao: str = Query(default=None)
):
    """Página de visualização da auditoria de agendamentos"""
    
    data_fim = datetime.now(tz_br)
    data_inicio = data_fim - timedelta(days=dias)
    
    registros = await buscar_auditoria(
        db=db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        acao=acao,
        limite=500
    )
    
    # Contadores por tipo de ação
    contadores = {}
    for reg in registros:
        contadores[reg.acao] = contadores.get(reg.acao, 0) + 1
    
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Auditoria de Agendamentos</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
            .filtros {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .contadores {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }}
            .contador {{ background: #007bff; color: white; padding: 10px 15px; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            th {{ background: #007bff; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            tr:hover {{ background: #f8f9fa; }}
            .acao-criado {{ color: #28a745; font-weight: bold; }}
            .acao-editado {{ color: #ffc107; font-weight: bold; }}
            .acao-cancelado_cliente, .acao-removido {{ color: #dc3545; font-weight: bold; }}
            select, input {{ padding: 8px; border: 1px solid #ddd; border-radius: 4px; }}
            button {{ background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Auditoria de Agendamentos</h1>
            
            <div class="filtros">
                <form method="get">
                    <label>Período: </label>
                    <select name="dias">
                        <option value="1" {'selected' if dias == 1 else ''}>Último dia</option>
                        <option value="7" {'selected' if dias == 7 else ''}>Últimos 7 dias</option>
                        <option value="30" {'selected' if dias == 30 else ''}>Últimos 30 dias</option>
                        <option value="90" {'selected' if dias == 90 else ''}>Últimos 90 dias</option>
                    </select>
                    
                    <label style="margin-left: 15px;">Ação: </label>
                    <select name="acao">
                        <option value="">Todas</option>
                        <option value="criado" {'selected' if acao == 'criado' else ''}>Criado</option>
                        <option value="editado" {'selected' if acao == 'editado' else ''}>Editado</option>
                        <option value="removido" {'selected' if acao == 'removido' else ''}>Removido</option>
                        <option value="cancelado_cliente" {'selected' if acao == 'cancelado_cliente' else ''}>Cancelado pelo Cliente</option>
                    </select>
                    
                    <button type="submit">Filtrar</button>
                </form>
            </div>
            
            <div class="contadores">
    """
    
    for acao_nome, qtd in contadores.items():
        html += f'<div class="contador">{acao_nome}: <strong>{qtd}</strong></div>'
    
    html += f"""
            </div>
            
            <p><strong>Total de registros:</strong> {len(registros)}</p>
            
            <table>
                <thead>
                    <tr>
                        <th>Data/Hora</th>
                        <th>Ação</th>
                        <th>Usuário</th>
                        <th>Cliente</th>
                        <th>Barbeiro</th>
                        <th>Data Agend.</th>
                        <th>Hora</th>
                        <th>IP</th>
                        <th>ID Agend.</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for reg in registros:
        data_local = reg.criada_em.astimezone(tz_br).strftime("%d/%m/%Y %H:%M:%S") if reg.criada_em else ""
        html += f"""
                    <tr>
                        <td>{data_local}</td>
                        <td class="acao-{reg.acao}">{reg.acao}</td>
                        <td>{reg.usuario_nome or '-'} <small>({reg.usuario_tipo})</small></td>
                        <td>{reg.cliente_nome or '-'}</td>
                        <td>{reg.barbeiro_nome or '-'}</td>
                        <td>{reg.data_agendamento or '-'}</td>
                        <td>{reg.hora_agendamento or '-'}</td>
                        <td>{reg.ip_origem or '-'}</td>
                        <td>#{reg.agendamento_id or '-'}</td>
                    </tr>
        """
    
    html += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    return html


@router.get("/download/{tipo}")
async def baixar_log(
    tipo: str,  # "app" ou "errors"
    request: Request,
    _=Depends(check_admin_session)
):
    """Baixa o arquivo de log atual"""
    log_file = Path(f"logs/{tipo}.log")
    if not log_file.exists():
        return {"erro": "Arquivo não encontrado"}
    return FileResponse(
        log_file,
        media_type="text/plain",
        filename=f"{tipo}_{datetime.now(tz_br).strftime('%Y%m%d')}.log"
    )
