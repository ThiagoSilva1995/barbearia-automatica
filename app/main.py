from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, Base, AsyncSessionLocal
from app.models.configuracao import Configuracao
from app.routers import (
    auth,
    agenda,
    cadastros,
    relatorios,
    cliente_publico,
    admin_config,
    fila_espera,
    api_clientes,
    api_agendamentos,
    notificacoes,  # ← NOVO: Router de notificações in-app
)
from app.services.reminder_service import loop_de_verificacao
from app.services.fila_inteligente_service import FilaInteligenteService
import os
import asyncio
import logging
from datetime import datetime

# Configuração básica de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def verificar_filas_expiradas_background():
    """
    Background task: Verifica filas expiradas a cada 1 minuto
    """
    while True:
        try:
            fila_service = FilaInteligenteService()
            await fila_service.verificar_expiracoes()
        except Exception as e:
            logger.error(f"Erro ao verificar filas expiradas: {e}")

        await asyncio.sleep(60)


async def lifespan(app: FastAPI):
    # Criar tabelas no banco
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Banco de dados pronto! (Tabelas verificadas)")

    # Inicia o robô de lembretes em segundo plano
    asyncio.create_task(loop_de_verificacao(AsyncSessionLocal))

    # Inicia verificador de filas expiradas
    asyncio.create_task(verificar_filas_expiradas_background())

    print("🤖 Robô de Lembretes e Fila Inteligente Iniciado...")

    yield


# Configuração da aplicação FastAPI com documentação completa
app = FastAPI(
    title="🏪 Barbearia do Thales - API",
    description="""
    # Sistema de Gestão para Barbearia
    
    API REST completa para gerenciamento de barbearia com:
    
    ## 🎯 Funcionalidades Principais
    
    - **📅 Agendamentos**: Sistema completo de agendamento online
    - **👤 Clientes**: Cadastro e gerenciamento de clientes
    - **💇 Barbeiros**: Gestão de equipe e horários
    - **✂️ Serviços**: Catálogo de serviços com preços e durações
    - **📦 Produtos**: Controle de estoque e vendas
    - **🤖 Automações**: Lembretes automáticos via WhatsApp
    - **📊 Relatórios**: Estatísticas e dashboards
    - **🔔 Notificações**: Sistema de notificações in-app
    
    ## 🚀 Endpoints Disponíveis
    
    ### Área Pública (Cliente)
    - `/cliente` - Acesso por telefone
    - `/cliente/agendar` - Agendamento online
    - `/cliente/meus-agendamentos` - Visualizar agendamentos
    
    ### Área Administrativa
    - `/home` - Dashboard principal
    - `/agendamentos` - Gestão de agenda
    - `/configuracoes` - Configurações do sistema
    
    ### API REST
    - `/api/clientes` - CRUD de clientes
    - `/api/agendamentos` - CRUD de agendamentos
    
    ## 📚 Documentação
    
    - **Swagger UI**: `/docs` (esta página)
    - **ReDoc**: `/redoc` (documentação alternativa)
    - **OpenAPI JSON**: `/openapi.json` (schema completo)
    
    ## 🔐 Autenticação
    
    A área administrativa requer login com senha configurada.
    A área do cliente usa apenas telefone para acesso.
    
    ## 🤖 Integrações
    
    - **WhatsApp**: Evolution API para mensagens automáticas
    - **Notificações**: Sistema in-app com sino 🔔
    - **Background Tasks**: Robôs de lembretes e aniversários
    
    ---
    
    **Desenvolvido com ❤️ usando FastAPI + Python**
    """,
    version="1.0.0",
    contact={
        "name": "Barbearia do Thales",
        "email": "contato@barberiathales.com.br",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {
            "name": "👤 Clientes",
            "description": "Operações com clientes (CRUD, busca, aniversariantes)",
        },
        {
            "name": "📅 Agendamentos",
            "description": "Operações com agendamentos (CRUD, pagamentos, filtros)",
        },
        {
            "name": "🔐 Autenticação",
            "description": "Login e logout do sistema administrativo",
        },
        {
            "name": "💇 Barbeiros",
            "description": "Gestão de barbeiros e equipe",
        },
        {
            "name": "✂️ Serviços",
            "description": "Catálogo de serviços oferecidos",
        },
        {
            "name": "📦 Produtos",
            "description": "Controle de estoque e produtos",
        },
        {
            "name": "⚙️ Configurações",
            "description": "Configurações do sistema e horários",
        },
        {
            "name": "📊 Relatórios",
            "description": "Estatísticas e dashboards",
        },
        {
            "name": "🔔 Notificações",
            "description": "Sistema de notificações in-app",
        },
    ],
    lifespan=lifespan,
)

# Middleware de sessão
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "sua_chave_secreta_forte_123"))

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
app.include_router(fila_espera.router)
app.include_router(notificacoes.router)  # ← NOVO: Notificações in-app

# Incluir routers de API REST
app.include_router(api_clientes.router)
app.include_router(api_agendamentos.router)


@app.get(
    "/health",
    tags=["🔧 Sistema"],
    summary="Health Check",
    description="Verifica se o sistema está funcionando corretamente."
)
async def health_check():
    """
    Endpoint de health check para monitoramento.
    
    Retorna status do sistema e timestamp atual.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get(
    "/",
    tags=["🔧 Sistema"],
    summary="Redirecionamento",
    description="Redireciona para a página inicial do sistema.",
    include_in_schema=False
)
async def root():
    """Redireciona para /home"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/home")


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
