import re
from django import template

register = template.Library()

@register.filter
def initials(value: str, max_letters: int = 2) -> str:
    """
    Devuelve las iniciales de un nombre. Ej: 'jonathan hernandez' -> 'JH'
    max_letters controla cuántas letras regresar (por defecto 2).
    """
    if not value:
        return ""
    # Toma la primera letra de cada palabra
    letters = re.findall(r"\b(\w)", value.strip(), flags=re.UNICODE)
    return "".join(letters[:int(max_letters)]).upper()
