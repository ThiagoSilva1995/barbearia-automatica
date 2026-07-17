import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

# Lê a URL do banco de dados das variáveis de ambiente
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./barbearia.db")

# Configuração do Engine
if DATABASE_URL.startswith("sqlite"):
    # Configurações específicas para SQLite
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    # Configurações para PostgreSQL (Produção/Fly.io)
    # NullPool é mais estável em ambientes serverless: cria e destrói conexões sob demanda
    # evitando o problema de "connection_lost" em conexões ociosas.
    
    # Detecta se é uma conexão interna do Fly.io (.internal)
    is_fly_internal = ".internal" in DATABASE_URL
    
    connect_args = {
        "server_settings": {
            "application_name": "barbearia_thales",
        },
        "timeout": 15,
        "command_timeout": 15,
    }
    
    # Em redes internas do Fly.io, o SSL pode causar problemas de handshake
    # Forçamos ssl=False para conexões .internal para evitar "connection_lost" durante o upgrade
    if is_fly_internal:
        connect_args["ssl"] = False

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args=connect_args,
    )

# Sessão Assíncrona
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


# Dependência para injetar a sessão nas rotas com retry automático
async def get_db():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()
            break  # Se chegou aqui, funcionou
        except Exception as e:
            error_str = str(e).lower()
            if "connection_lost" in error_str or "connectionerror" in error_str or "closed" in error_str:
                if attempt < max_retries - 1:
                    logger_msg = f"⚠️ Conexão perdida, tentando novamente ({attempt + 1}/{max_retries})..."
                    print(logger_msg)
                    await asyncio.sleep(0.5 * (2 ** attempt))  # Exponential backoff
                    continue
            raise


# Função de inicialização (cria as tabelas se não existirem)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Banco de dados conectado e tabelas verificadas!")
