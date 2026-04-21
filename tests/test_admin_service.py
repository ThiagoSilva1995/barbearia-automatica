# tests/test_admin_service.py
import pytest
from datetime import date
from sqlalchemy import select
from app.models import Cliente
from app.services import admin_service


class TestAdminServiceClientes:
    """Testes para funções do admin_service relacionadas a clientes"""

    @pytest.mark.asyncio
    async def test_criar_cliente_service(self, db_session):
        """Testa criação de cliente via service"""
        cliente = await admin_service.criar_cliente(
            db=db_session,
            nome="Teste Service",
            telefone="(71) 98888-7777",
            data_nascimento=date(1992, 8, 20),
        )

        assert cliente.id is not None
        assert cliente.nome == "Teste Service"
        assert cliente.telefone == "5571988887777"
        assert cliente.data_nascimento == date(1992, 8, 20)

    @pytest.mark.asyncio
    async def test_atualizar_cliente_service(self, db_session):
        """Testa atualização de cliente via service"""
        # Criar cliente
        cliente = await admin_service.criar_cliente(
            db=db_session,
            nome="Original",
            telefone="73911112222",
            data_nascimento=date(1990, 1, 1),
        )

        # Atualizar
        await admin_service.atualizar_cliente(
            db=db_session,
            cliente_id=cliente.id,
            nome="Atualizado",
            telefone="(73) 92222-3333",
            data_nascimento=date(1995, 5, 10),
        )

        # Verificar com select() (SQLAlchemy 2.0)
        stmt = select(Cliente).where(Cliente.id == cliente.id)
        result = await db_session.execute(stmt)
        updated = result.scalars().first()

        assert updated is not None
        assert updated.nome == "Atualizado"
        assert updated.telefone == "5573922223333"
        assert updated.data_nascimento == date(1995, 5, 10)

    @pytest.mark.asyncio
    async def test_get_clientes_com_visitas(self, db_session):
        """Testa busca de clientes com contagem de visitas"""
        # Criar alguns clientes de teste
        await admin_service.criar_cliente(
            db=db_session,
            nome="Cliente A",
            telefone="73911111111",
            data_nascimento=date(1990, 1, 1),
        )
        await admin_service.criar_cliente(
            db=db_session,
            nome="Cliente B",
            telefone="73922222222",
            data_nascimento=date(1991, 2, 2),
        )

        # Buscar com visitas
        resultado = await admin_service.get_clientes_com_visitas(db_session)

        assert len(resultado) >= 2
        assert all(
            "cliente" in item and "visitas_ultima_semana" in item for item in resultado
        )
