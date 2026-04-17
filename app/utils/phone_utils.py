# app/utils/phone_utils.py
import re


def format_phone_for_storage(phone: str) -> str:
    """
    Padroniza telefone para armazenamento no banco:
    - Remove tudo que não é dígito
    - Garante prefixo 55 (Brasil)
    - Retorna apenas dígitos: 5573999999999
    """
    # Remove tudo que não é dígito
    digits = re.sub(r"\D", "", phone)

    # Remove zeros à esquerda após o código do país (se houver)
    digits = digits.lstrip("0")

    # Se não tem 55 no início, adiciona
    if not digits.startswith("55"):
        digits = "55" + digits

    # Garante que tem pelo menos 13 dígitos (55 + DDD + 9 dígitos)
    # Se tiver mais (ex: código de operadora), mantém como está
    return digits


def format_phone_for_display(phone: str) -> str:
    """
    Formata telefone do banco para exibição legível:
    Entrada: 5573999999999
    Saída: +55 (73) 99999-9999  ou  +55 (73) 9999-9999
    """
    # Remove tudo que não é dígito para garantir
    digits = re.sub(r"\D", "", phone)

    # Remove 55 do início para formatar o resto
    if digits.startswith("55"):
        digits = digits[2:]

    # Separa DDD e número
    if len(digits) >= 10:
        ddd = digits[:2]
        number = digits[2:]

        # Celular (9 dígitos) ou Fixo (8 dígitos)
        if len(number) == 9:
            # Celular: 9XXXX-XXXX
            formatted = f"+55 ({ddd}) {number[:5]}-{number[5:]}"
        elif len(number) == 8:
            # Fixo: XXXX-XXXX
            formatted = f"+55 ({ddd}) {number[:4]}-{number[4:]}"
        else:
            # Fallback: agrupa de 5 em 5
            formatted = f"+55 ({ddd}) {' '.join([number[i:i+5] for i in range(0, len(number), 5)])}"
    else:
        # Não conseguiu formatar, retorna como está com +55
        formatted = f"+55 {digits}"

    return formatted


def normalize_phone_for_search(phone: str) -> str:
    """
    Extrai apenas os últimos 9-11 dígitos para busca flexível.
    Útil para encontrar cliente mesmo se digitou com/sem 55, com/sem DDD.
    """
    digits = re.sub(r"\D", "", phone)
    # Retorna os últimos 9 dígitos (número) + DDD se disponível
    return digits[-11:] if len(digits) >= 11 else digits[-9:]
