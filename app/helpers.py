from __future__ import annotations
from datetime import date, timedelta, datetime
from typing import Dict, Optional
from django.utils import timezone
from functools import wraps
from typing import Iterable, Optional, Callable
from django.http import HttpResponseForbidden, HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url
from django.conf import settings
from django.shortcuts import render


def role_required(allowed_roles: Iterable[str]):
    allowed = set(allowed_roles)

    def decorator(view_func: Callable):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not request.user.is_authenticated:
                login_url = resolve_url(getattr(settings, "LOGIN_URL", "app.login"))
                return redirect(f"{login_url}?next={request.get_full_path()}")

            # 2) Ensure gym_user exists
            gp = getattr(request, "gym_user", None)
            role = getattr(request, "gym_role", None)

            if gp is None or role is None:
                return render(
                    request,
                    "403.html",
                    {"message": "You do not have a gym profile configured."},
                    status=403,
                )

            # 3) Role check
            if role not in allowed:
                return render(
                    request,
                    "403.html",
                    {"message": "Your role has not permission to access this page"},
                    status=403,
                )

            # All good
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def gym_required(view_func: Callable):
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if getattr(request, "gym", None) is None:
            return render(
                    request,
                    "403.html",
                    {"message": "YYou must select a gym before accessing this page."},
                    status=403,
                )

        return view_func(request, *args, **kwargs)

    return _wrapped


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

WEEKDAYS_ES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

def format_es_date(
    d: date | datetime | None,
    include_year: bool | None = None,
    include_weekday: bool = False,
) -> str:
    """
    Ejemplos:
      - format_es_date(d)                       -> "2 de septiembre"
      - format_es_date(d, include_year=True)    -> "2 de septiembre de 2024"
      - format_es_date(d, include_weekday=True) -> "Martes, 2 de septiembre de 2024" (si corresponde incluir año)
    Reglas de `include_year`:
      - True  -> siempre incluye año
      - False -> nunca incluye año
      - None  -> incluye año solo si d.year != año actual
    """
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = timezone.localtime(d).date()

    today = timezone.localdate()
    if include_year is None:
        include_year = (d.year != today.year)

    text = f"{d.day} de {MONTHS_ES[d.month - 1]}"
    if include_year:
        text += f" de {d.year}"

    if include_weekday:
        weekday = WEEKDAYS_ES[d.weekday()]  # Monday=0
        text = f"{weekday} {text}"

    return text

