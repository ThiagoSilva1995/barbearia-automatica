# tests/test_phone_utils.py
import pytest
from app.utils.phone_utils import (
    format_phone_for_storage,
    format_phone_for_display,
    normalize_phone_for_search,
)


class TestFormatPhoneForStorage:
    """Testes para format_phone_for_storage"""

    def test_format_with_parentheses_and_dash(self):
        """Testa telefone com formatação comum"""
        result = format_phone_for_storage("(73) 99999-9999")
        assert result == "5573999999999"

    def test_format_with_spaces(self):
        """Testa telefone com espaços"""
        result = format_phone_for_storage("73 9 9999 9999")
        assert result == "5573999999999"

    def test_format_already_with_55(self):
        """Testa telefone que já tem 55"""
        result = format_phone_for_storage("5573999999999")
        assert result == "5573999999999"

    def test_format_without_country_code(self):
        """Testa telefone sem código do país"""
        result = format_phone_for_storage("73999999999")
        assert result == "5573999999999"

    def test_format_with_plus_sign(self):
        """Testa telefone com +"""
        result = format_phone_for_storage("+55 (73) 99999-9999")
        assert result == "5573999999999"

    def test_format_landline_8_digits(self):
        """Testa telefone fixo com 8 dígitos"""
        result = format_phone_for_storage("(73) 3333-4444")
        assert result == "557333334444"


class TestFormatPhoneForDisplay:
    """Testes para format_phone_for_display"""

    def test_format_mobile_9_digits(self):
        """Testa exibição de celular com 9 dígitos"""
        result = format_phone_for_display("5573999999999")
        assert result == "+55 (73) 99999-9999"

    def test_format_landline_8_digits(self):
        """Testa exibição de fixo com 8 dígitos"""
        result = format_phone_for_display("557333334444")
        assert result == "+55 (73) 3333-4444"

    def test_format_with_plus_already(self):
        """Testa telefone que já tem +"""
        result = format_phone_for_display("+5573999999999")
        assert result == "+55 (73) 99999-9999"


class TestNormalizePhoneForSearch:
    """Testes para normalize_phone_for_search"""

    def test_extract_last_11_digits(self):
        """Testa extração dos últimos 11 dígitos (sem adicionar 55)"""
        # A função apenas extrai dígitos, não adiciona código do país
        result = normalize_phone_for_search("5573999999999")
        assert result == "73999999999"  # Últimos 11 dígitos sem o 55 inicial

    def test_extract_last_9_digits(self):
        """Testa extração dos últimos 9 dígitos"""
        result = normalize_phone_for_search("999999999")
        assert result == "999999999"

    def test_with_formatting_characters(self):
        """Testa com caracteres de formatação"""
        result = normalize_phone_for_search("(73) 99999-9999")
        assert result == "73999999999"

    def test_with_country_code_variations(self):
        """Testa que a função extrai consistentemente os últimos dígitos"""
        # Todos devem retornar os mesmos últimos 11 dígitos
        assert normalize_phone_for_search("5573999999999") == "73999999999"
        assert normalize_phone_for_search("73999999999") == "73999999999"
        assert normalize_phone_for_search("(73) 99999-9999") == "73999999999"
