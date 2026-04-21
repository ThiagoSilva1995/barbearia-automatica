# tests/test_api_clientes.py
import pytest
from datetime import date
from urllib.parse import unquote
from sqlalchemy import select
from app.models import Cliente


class TestClienteCadastro:
    """Testes para cadastro de clientes via API"""

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_sucesso(self, client, db_session):
        """Testa cadastro de cliente com sucesso"""
        response = client.post(
            "/cadastrar-cliente",
            data={
                "nome": "João Silva",
                "telefone": "(73) 99999-9999",
                "data_nascimento": "1990-01-01",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303  # Redirect
        assert "msg=sucesso" in response.headers["location"]

        # Verificar no banco com select() (SQLAlchemy 2.0)
        stmt = select(Cliente).where(Cliente.nome == "João Silva")
        result = await db_session.execute(stmt)
        cliente = result.scalars().first()
        assert cliente is not None
        assert cliente.telefone == "5573999999999"

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_telefone_duplicado(self, client, db_session):
        """Testa tentativa de cadastrar telefone já existente"""
        # Primeiro cadastro
        client.post(
            "/cadastrar-cliente",
            data={
                "nome": "Maria Souza",
                "telefone": "73988887777",
                "data_nascimento": "1985-05-15",
            },
            follow_redirects=False,
        )

        # Tentar cadastrar mesmo telefone
        response = client.post(
            "/cadastrar-cliente",
            data={
                "nome": "Outra Pessoa",
                "telefone": "(73) 98888-7777",  # Mesmo número, formato diferente
                "data_nascimento": "1992-03-20",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "erro" in response.headers["location"]
        # Verificar mensagem URL-decoded
        location_decoded = unquote(response.headers["location"])
        assert "Telefone já cadastrado" in location_decoded

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_campos_obrigatorios(self, client):
        """Testa validação de campos obrigatórios"""
        response = client.post(
            "/cadastrar-cliente",
            data={
                "nome": "",  # Nome vazio
                "telefone": "73999999999",
                "data_nascimento": "1990-01-01",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "erro" in response.headers["location"]


class TestClienteEdicao:
    """Testes para edição de clientes via API"""

    @pytest.mark.asyncio
    async def test_editar_cliente_sucesso(self, client, db_session):
        """Testa edição de cliente com sucesso"""
        # Criar cliente primeiro (SEM await no add)
        novo_cliente = Cliente(
            nome="Cliente Original",
            telefone="557311112222",
            data_nascimento=date(1990, 1, 1),
        )
        db_session.add(novo_cliente)  # ← SEM await!
        await db_session.commit()

        # Buscar o cliente criado
        stmt = select(Cliente).where(Cliente.telefone == "557311112222")
        result = await db_session.execute(stmt)
        cliente = result.scalars().first()

        # Editar cliente
        response = client.post(
            f"/editar-cliente/{cliente.id}",
            data={
                "nome": "Cliente Atualizado",
                "telefone": "(73) 93333-4444",
                "data_nascimento": "1995-06-15",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "msg=Cliente+atualizado" in response.headers["location"]

        # Verificar atualização no banco
        await db_session.refresh(cliente)
        assert cliente.nome == "Cliente Atualizado"
        assert cliente.telefone == "5573933334444"
