from __future__ import annotations
from datetime import date, timedelta, datetime
from typing import Dict, Optional
from django.utils import timezone
from functools import wraps
from typing import Iterable, Optional
from django.http import HttpResponseForbidden, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from app.models import GymUser

def _get_gym_user_for_request(request):
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return None
    return getattr(u, "gym_profile", None)


def role_required(roles: Iterable[str], forbid: bool = False):
    roles_set = set(roles)
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not request.user.is_authenticated:
                return redirect(f"{reverse('app.login')}?next={request.get_full_path()}")
            gu = _get_gym_user_for_request(request)
            if not gu:
                return redirect("app.home")
            if gu.role not in roles_set:
                if forbid:
                    return redirect("app.home")
                return redirect("app.home")
            request.gym_user = gu
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


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
