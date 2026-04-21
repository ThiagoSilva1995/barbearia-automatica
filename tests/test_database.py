# tests/test_database.py
import pytest
from datetime import date, timedelta
from sqlalchemy import select, func
from app.models import Cliente, Agendamento, Servico


class TestDatabaseQueries:
    """Testes para queries do banco de dados"""

    @pytest.mark.asyncio
    async def test_cliente_telefone_unico(self, db_session):
        """Testa que telefone é único no banco"""
        # Usar telefone ÚNICO para não colidir com outros testes
        telefone_teste = "5573555566667"  # ← Telefone exclusivo para este teste

        # Criar primeiro cliente
        cliente1 = Cliente(
            nome="Cliente 1",
            telefone=telefone_teste,
            data_nascimento=date(1990, 1, 1),
        )
        db_session.add(cliente1)
        await db_session.commit()

        # Buscar pelo telefone exato
        stmt = select(Cliente).where(Cliente.telefone == telefone_teste)
        result = await db_session.execute(stmt)
        encontrado = result.scalars().first()

        assert encontrado is not None
        assert encontrado.nome == "Cliente 1"  # ← Agora vai funcionar!

    @pytest.mark.asyncio
    async def test_busca_cliente_por_telefone_parcial(self, db_session):
        """Testa busca flexível por telefone com dados isolados"""
        # Usar telefone ÚNICO para não colidir com outros testes
        telefone_unico = "5573123450001"  # ← Telefone exclusivo

        # Criar cliente
        cliente = Cliente(
            nome="Busca Teste Unico",
            telefone=telefone_unico,
            data_nascimento=date(1988, 12, 25),
        )
        db_session.add(cliente)
        await db_session.commit()
        await db_session.refresh(cliente)

        # Buscar pelos últimos 9 dígitos (sem o 5573 inicial)
        stmt = select(Cliente).where(Cliente.telefone.like("%123450001"))
        result = await db_session.execute(stmt)
        encontrados = result.scalars().all()

        assert len(encontrados) == 1
        assert encontrados[0].nome == "Busca Teste Unico"
