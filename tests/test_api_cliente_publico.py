# tests/test_api_cliente_publico.py
import pytest
from datetime import date, time
from urllib.parse import unquote
from sqlalchemy import select
from app.models import Cliente, Barbeiro, Servico, Agendamento


class TestAreaClienteAcesso:
    """Testes para tela de acesso do cliente"""

    @pytest.mark.asyncio
    async def test_get_area_cliente_acesso(self, client):
        """Testa acesso à tela de login do cliente"""
        response = client.get("/cliente")

        assert response.status_code == 200
        # Verificar conteúdo decodificado
        content = response.content.decode("utf-8").lower()
        assert "bem-vindo" in content or "agende" in content or "whatsapp" in content


class TestClienteAcessar:
    """Testes para login do cliente"""

    @pytest.mark.asyncio
    async def test_acessar_cliente_existente(self, client, db_session):
        """Testa login de cliente cadastrado"""
        # Arrange: Criar cliente
        cliente = Cliente(
            nome="Login Teste",
            telefone="5573123456789",
            data_nascimento=date(1991, 2, 2),
        )
        db_session.add(cliente)
        await db_session.commit()

        # Act: Tentar login com telefone formatado diferente
        response = client.post(
            "/cliente/acessar",
            data={"telefone": "(73) 12345-6789"},  # Formato diferente do banco
            follow_redirects=False,
        )

        # Assert: Deve redirecionar para área do cliente
        assert response.status_code == 303
        assert "/cliente/meus-agendamentos" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_acessar_cliente_nao_existente(self, client):
        """Testa login com telefone não cadastrado"""
        response = client.post(
            "/cliente/acessar",
            data={"telefone": "73900000000"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/cliente/cadastro" in response.headers["location"]
        # Verifica que telefone foi passado para pré-preencher
        assert "telefone=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_acessar_telefone_vazio(self, client):
        """Testa validação de telefone obrigatório"""
        response = client.post(
            "/cliente/acessar",
            data={"telefone": ""},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "erro" in response.headers["location"]


class TestClienteCadastrar:
    """Testes para cadastro de novo cliente (área pública)"""

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_novo_sucesso(self, client, db_session):
        """Testa cadastro completo de novo cliente"""
        response = client.post(
            "/cliente/cadastrar",
            data={
                "nome": "Novo Cliente",
                "telefone": "(71) 98765-4321",
                "data_nascimento": "1994-12-25",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/cliente/meus-agendamentos" in response.headers["location"]

        # Verificar no banco
        stmt = select(Cliente).where(Cliente.telefone == "5571987654321")
        result = await db_session.execute(stmt)
        cliente = result.scalars().first()

        assert cliente is not None
        assert cliente.nome == "Novo Cliente"
        assert cliente.data_nascimento == date(1994, 12, 25)

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_telefone_ja_cadastrado(self, client, db_session):
        """Testa tentativa de cadastrar telefone duplicado"""
        # Primeiro cadastro
        cliente_existente = Cliente(
            nome="Existente",
            telefone="5573555556666",
            data_nascimento=date(1990, 1, 1),
        )
        db_session.add(cliente_existente)
        await db_session.commit()

        # Tentar cadastrar mesmo telefone
        response = client.post(
            "/cliente/cadastrar",
            data={
                "nome": "Outra Pessoa",
                "telefone": "(73) 55555-6666",  # Mesmo número, formato diferente
                "data_nascimento": "1995-5-5",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        location_decoded = unquote(response.headers["location"])
        assert "erro" in location_decoded
        assert "Telefone já cadastrado" in location_decoded

    @pytest.mark.asyncio
    async def test_cadastrar_cliente_campos_obrigatorios(self, client):
        """Testa validação de campos obrigatórios no cadastro público"""
        response = client.post(
            "/cliente/cadastrar",
            data={
                "nome": "",  # Vazio
                "telefone": "73999999999",
                "data_nascimento": "1990-01-01",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "erro" in response.headers["location"]


class TestClienteAgendar:
    """Testes para fluxo de agendamento do cliente"""

    @pytest.mark.asyncio
    async def test_get_agendar_form_sem_login(self, client):
        """Testa que agendar sem login redireciona para login"""
        response = client.get("/cliente/agendar", follow_redirects=False)

        # Se não logado, deve redirecionar
        assert response.status_code == 303
        assert "/cliente" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_post_agendar_confirmar_sem_login(self, client):
        """Testa tentativa de agendar sem estar logado"""
        response = client.post(
            "/cliente/agendar/confirmar",
            data={
                "servico": ["1"],
                "hora": "14:30",
                "barbeiro": "1",
                "data": "2026-05-20",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/cliente" in response.headers["location"]


class TestClienteCancelar:
    """Testes para cancelamento de agendamento"""

    @pytest.mark.asyncio
    async def test_cancelar_sem_login(self, client):
        """Testa tentativa de cancelar sem estar logado"""
        response = client.get("/cliente/cancelar/1", follow_redirects=False)

        assert response.status_code == 303
        assert "/cliente" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_cancelar_agendamento_nao_existente(self, client, db_session):
        """Testa cancelamento de ID inexistente (com session mock)"""
        # Este teste requer mock de session - simplificado aqui
        # Em implementação real, usar fixture de autenticação
        pass  # Placeholder para teste com autenticação


class TestClienteSair:
    """Testes para logout do cliente"""

    @pytest.mark.asyncio
    async def test_cliente_sair_redirect(self, client):
        """Testa que logout redireciona para página inicial"""
        # Teste simplificado: apenas verifica que a rota existe e redireciona
        response = client.get("/cliente/sair", follow_redirects=False)

        # Pode ser 303 (redirect) ou 200 se já não logado
        assert response.status_code in [200, 303]
