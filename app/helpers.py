# app/helpers.py
from __future__ import annotations

from datetime import date, timedelta, datetime
from typing import Dict, Optional
from django.utils import timezone

# -----------------------------
# Formatting helpers
# -----------------------------
def signed_at_parts(dt) -> Dict[str, Optional[str]]:
    """
    Return {'day': 'today'|'yesterday'|dd/mm/yy, 'time': 'h:mm AM/PM'} for a timezone-aware datetime.
    If dt is None, both values are None.
    """
    if dt is None:
        return {"day": None, "time": None}

    local_dt = timezone.localtime(dt)  # convert to project timezone
    today = timezone.localdate()
    d = local_dt.date()

    # Label for day
    if d == today:
        day_label = "today"
    elif d == (today - timedelta(days=1)):
        day_label = "yesterday"
    else:
        day_label = local_dt.strftime("%d/%m/%y")  # dd/mm/yy

    # 12h time like "1:05 PM" (no leading zero)
    time_12h = local_dt.strftime("%I:%M %p").lstrip("0")

    return {"day": day_label, "time": time_12h}

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

def format_es_date(d: date | datetime | None, include_year: bool | None = None) -> str:
    """
    Formatea fechas como:
      - "8 de septiembre"
      - "9 de agosto de 2023"
    include_year:
      - True  -> siempre incluye año
      - False -> nunca incluye año
      - None  -> incluye año solo si d.year != año actual
    Acepta date o datetime. Si d es None, retorna "".
    """
    if d is None:
        return ""
    if isinstance(d, datetime):
        # Convierte a fecha en tz local para coherencia
        d = timezone.localtime(d).date()

    day = d.day
    month_name = MONTHS_ES[d.month - 1]
    if include_year is None:
        include_year = (d.year != timezone.localdate().year)

    return f"{day} de {month_name}" + (f" de {d.year}" if include_year else "")
