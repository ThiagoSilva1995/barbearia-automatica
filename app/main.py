from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, Base, AsyncSessionLocal
from app.routers import fila_manual
from app.models.configuracao import Configuracao
from app.routers import (
    auth,
    agenda,
    cadastros,
    relatorios,
    cliente_publico,
    admin_config,
    # fila_espera,  # ← COMENTADO: Router da fila inteligente desativado
)
from app.services.reminder_service import loop_de_verificacao

# from app.services.fila_inteligente_service import FilaInteligenteService  # ← COMENTADO
from app.atualizar_tabelas import executar_migracoes

import os
import asyncio
import logging
from datetime import datetime

# Configuração básica de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


# async def verificar_filas_expiradas_background():  # ← COMENTADO
#     """
#     Background task: Verifica filas expiradas a cada 1 minuto
#     """
#     while True:
#         try:
#             fila_service = FilaInteligenteService()
#             await fila_service.verificar_expiracoes()
#         except Exception as e:
#             logger.error(f"Erro ao verificar filas expiradas: {e}")
#         await asyncio.sleep(60)


async def lifespan(app: FastAPI):
    # Criar tabelas no banco (tabelas novas)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Banco de dados pronto! (Tabelas verificadas)")

    # Executar migrações para adicionar colunas faltantes em tabelas existentes
    try:
        async with AsyncSessionLocal() as db:
            await executar_migracoes(db)
    except Exception as e:
        logger.error(f"⚠️ Erro nas migrações: {e}")

    # Inicia o robô de lembretes em segundo plano
    asyncio.create_task(loop_de_verificacao(AsyncSessionLocal))

    # ← COMENTADO: Inicia verificador de filas expiradas
    # asyncio.create_task(verificar_filas_expiradas_background())

    print("🤖 Robô de Lembretes Iniciado... (Fila Inteligente desativada)")

    yield


app = FastAPI(title="Gestão de Barbearia", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="sua_chave_secreta_forte_123")

# Configurar static files
static_path = "app/static"
if not os.path.exists(static_path):
    os.makedirs(static_path)
    with open(os.path.join(static_path, "manifest.json"), "w", encoding="utf-8") as f:
        f.write("{}")

app.mount("/static", StaticFiles(directory=static_path), name="static")

# Incluir routers
app.include_router(auth.router)
app.include_router(agenda.router)
app.include_router(cadastros.router)
app.include_router(relatorios.router)
app.include_router(cliente_publico.router)
app.include_router(admin_config.router)
app.include_router(fila_manual.router)
# app.include_router(fila_espera.router)  # ← COMENTADO: Router da fila inteligente


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
