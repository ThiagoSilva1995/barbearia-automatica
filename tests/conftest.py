# tests/conftest.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient

# URL do banco de teste (SQLite em memória para velocidade)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Cria um event loop para testes async"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def engine():
    """Cria engine de teste com SQLite em memória"""
    return create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session")
async def session_factory(engine):
    """Cria factory de sessões para testes"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    yield async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(session_factory):
    """Cria uma sessão de banco para cada teste"""
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def override_get_db(db_session):
    """Override do get_db para usar sessão de teste"""

    async def _get_db():
        yield db_session

    return _get_db


@pytest.fixture
def client(override_get_db):
    """Cria cliente de teste com dependências override"""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}
