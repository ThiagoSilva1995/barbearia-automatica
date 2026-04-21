def format_name(name: str) -> str:
    """Formata nome para Title Case: 'thiago silva' → 'Thiago Silva'"""
    if not name:
        return ""
    return " ".join(name.strip().split()).title()
