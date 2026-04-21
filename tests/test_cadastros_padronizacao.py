# tests/test_cadastros_padronizacao.py
"""
Testes de padronização de nomes para cadastros
Foco em testes unitários da função format_name()
"""

import pytest
from app.utils.formatters import format_name


class TestFormatNameCadastros:
    """Testes unitários para formatação de nomes em cadastros"""

    def test_format_barbeiro_nome(self):
        """Testa formatação de nome de barbeiro"""
        assert format_name("carlos eduardo") == "Carlos Eduardo"
        assert format_name("MARIA JOSE") == "Maria Jose"
        assert format_name("  joao  silva  ") == "Joao Silva"

    def test_format_servico_nome(self):
        """Testa formatação de nome de serviço"""
        assert format_name("CORTE DE CABELO") == "Corte De Cabelo"
        assert format_name("barba e bigode") == "Barba E Bigode"
        assert format_name("hidratação profunda") == "Hidratação Profunda"

    def test_format_produto_nome(self):
        """Testa formatação de nome de produto"""
        assert format_name("pomada modeladora") == "Pomada Modeladora"
        assert format_name("SHAMPOO HIDRATANTE") == "Shampoo Hidratante"
        assert format_name("gel fixação forte") == "Gel Fixação Forte"

    def test_format_edge_cases(self):
        """Testa casos especiais de formatação"""
        # Nomes vazios
        assert format_name("") == ""
        assert format_name("   ") == ""

        # Nomes com acentos
        assert format_name("joão silva") == "João Silva"
        assert format_name("MARIA JOSÉ") == "Maria José"

        # Nomes compostos
        assert format_name("ana clara sousa") == "Ana Clara Sousa"
        assert format_name("CARLOS EDUARDO SILVA") == "Carlos Eduardo Silva"
