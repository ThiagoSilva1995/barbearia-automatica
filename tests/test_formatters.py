# tests/test_formatters.py
import pytest
from app.utils.formatters import format_name


class TestFormatName:
    """Testes para formatação de nomes"""

    def test_nome_minusculo(self):
        assert format_name("thiago silva") == "Thiago Silva"

    def test_nome_maiusculo(self):
        assert format_name("THIAGO SILVA") == "Thiago Silva"

    def test_nome_misto(self):
        assert format_name("Thiago silva DOS santos") == "Thiago Silva Dos Santos"

    def test_nome_com_espacos_extras(self):
        assert format_name("  thiago   silva  ") == "Thiago Silva"

    def test_nome_vazio(self):
        assert format_name("") == ""

    def test_nome_com_acentos(self):
        assert format_name("joão silva") == "João Silva"
        assert format_name("MARIA JOSÉ") == "Maria José"
