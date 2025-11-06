from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from .helpers import (
    signed_at_parts,
    format_es_date,
    role_required,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from urllib.parse import urlencode
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponseBadRequest
from app.models import GymUser
from datetime import date, timedelta
from .models import DailyTimeslot, GymUser, BaseTimeslot, Payment
from dateutil.relativedelta import relativedelta
from django.db.models import Max, Sum
from calendar import monthrange
from django.db import transaction
from django.views.decorators.http import require_http_methods


@login_required
def index(request):
    return render(request, "app/home.html")

@login_required
@role_required(["admin"])
def admin(request):
    today = timezone.localdate()

    active_members = GymUser.objects.filter(is_active=True).count()

    qs = Payment.objects.all()
    qs = qs.filter(period_start__lte=today, period_end__gt=today)

    period_income = qs.aggregate(total=Sum("amount"))["total"] or 0

    ctx = {
        "active_members": active_members,
        "period_income": period_income,
        "period_label": _period_label(today.year, today.month)
    }
    return render(request, "app/admin.html", ctx)



@require_http_methods(["GET", "POST"])
def base_hours(request):

    tomorrow = timezone.localdate() + timedelta(days=1)

    if request.method == "POST":
        created = 0
        skipped = 0

        base_qs = BaseTimeslot.objects.only("id", "title", "capacity", "is_active").filter(is_active=True)

        with transaction.atomic():
            for b in base_qs:
                obj, made = DailyTimeslot.objects.get_or_create(
                    base=b,
                    slot_date=tomorrow,
                    defaults={
                        "title": b.title,
                        "capacity": b.capacity,
                        "status": "open",
                    },
                )
                if made:
                    created += 1
                else:
                    skipped += 1

        # Redirige para evitar reenvío del form (PRG)
        return redirect("app.base_hours")

    qs = (
        BaseTimeslot.objects
        .only("id", "title", "capacity", "is_active")
        .order_by("id")
    )

    hours = [
        {
            "id": h.id,
            "title": h.title,
            "capacity": h.capacity,
            "is_active": h.is_active,
            "is_active_label": "Activo" if h.is_active else "Inactivo",
        }
        for h in qs
    ]

    already_created = DailyTimeslot.objects.filter(slot_date=tomorrow).exists()
    ctx = {
        "hours": hours,
        "tomorrow": tomorrow, 
        "already_created_for_tomorrow": already_created,
    }
    return render(request, "app/base_hours.html", ctx)



def selector(request):
    return render(request, "app/hourselection.html")


def _current_period_for(user: GymUser, ref: date | None = None) -> tuple[date, date]:
    today = ref or timezone.localdate()
    anchor = user.join_date.day
    if today.day < anchor:
        start = (today.replace(day=1) - relativedelta(months=1)).replace(day=anchor)
    else:
        start = today.replace(day=anchor)
    end = start + relativedelta(months=1)  # exclusivo
    return start, end


def users(request):
    filt = (request.GET.get("filter") or "all").strip().lower()
    delinquent_days = int(request.GET.get("days") or 30)

    today = timezone.localdate()
    qs = (
        GymUser.objects
        .filter(is_active=True)
        .only("id", "full_name", "join_date")
        .order_by("full_name")
    )

    out = []
    for u in qs:
        ps, pe = _current_period_for(u, ref=today)
        paid = Payment.objects.filter(
            user=u, period_start__lte=ps, period_end__gte=pe
        ).exists()

        agg = Payment.objects.filter(user=u).aggregate(last_end=Max("period_end"))
        last_end = agg["last_end"]
        if last_end:
            last_covered_day = last_end - timedelta(days=1)
            days_since_last_cover = (today - last_covered_day).days
        else:
            days_since_last_cover = 10**9

        days_to_due = (pe - today).days
        include = False
        if filt == "overdue":
            include = (not paid)
        elif filt == "delinquent":
            include = (not paid) and (days_since_last_cover > delinquent_days)
        elif filt == "up_to_date":
            include = paid
        elif filt == "due_in_3":
            include = (1 <= days_to_due <= 3)
        elif filt == "due_in_7":
            include = (1 <= days_to_due <= 7)
        else:  # "all" (o cualquier otro valor)
            include = True

        if include:
            _, de = _current_period_for(u)
            out.append({
                "id": u.id,
                "full_name": u.full_name,
                "next_payment_date": format_es_date(de),
                "paid_current_period": paid,
            })

    return render(request, "app/users.html", {"users": out, "filter": filt})


@login_required
@role_required(["admin", "member"])
def profile(request):
    raw = request.GET.get("userid")
    if not raw:
        return HttpResponseBadRequest("Falta el parámetro ?userid")

    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("userid inválido")

    user = get_object_or_404(
        GymUser.objects.prefetch_related(
            "weights",
        ).only(
            "id", "full_name", "role", "join_date", "birth_date", "phone",
            "is_active", "created_at", "updated_at",
        ),
        pk=user_id,
    )

    last_weight = user.weights.order_by("-recorded_at").first()
    weight = None
    if last_weight:
        weight = {
            "id": last_weight.id,
            "weight_kg": float(last_weight.weight_kg),
            "recorded_at": timezone.localtime(last_weight.recorded_at) if last_weight.recorded_at else None,
        }


    ps, pe = _current_period_for(user)
    has_paid = Payment.objects.filter(
        user=user, period_start__lte=ps, period_end__gte=pe
    ).exists()

    last_payment = (
            Payment.objects
            .filter(user=user)
            .order_by("-period_end")
            .only("id", "paid_at", "period_start", "period_end", "period_label")
            .first()
        )

    last_payment_info = None
    if last_payment:
        last_payment_info = {
            "id": last_payment.id,
            "paid_at": format_es_date(last_payment.paid_at, include_year=True) if last_payment.paid_at else "",
            # usa el label guardado si existe; si no, lo calculamos desde period_start
            "period_paid_label": (
                last_payment.period_label
                if getattr(last_payment, "period_label", None)
                else _period_label(last_payment.period_start.year, last_payment.period_start.month)
            ),
        }



    ctx = {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "phone": getattr(user, "phone", None),
            "next_payment_date": format_es_date(pe),
            "has_paid": has_paid,
            "join_date": format_es_date(user.join_date, include_year=True),
            "birth_date": format_es_date(user.birth_date, include_year=True),
            "is_active": user.is_active,
            "height_cm": user.height_cm,
            "weight": weight,
            "last_payment": last_payment_info,
        }
    }
    return render(request, "app/profile.html", ctx)

def hours(request):
    q = request.GET.get("date")
    day = parse_date(q) if q else None
    if day is None:
        day = timezone.localdate()

    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    slots = (
        DailyTimeslot.objects
        .filter(slot_date=day)
        .order_by("title")
        .prefetch_related("signups__user")
    )

    data = []
    for s in slots:
        users = [
            {
                "id": su.user_id,
                "full_name": su.user.full_name,
                "phone": su.user.phone,
                "signed_at": signed_at_parts(su.signed_at),
            }
            for su in s.signups.all()
        ]
        data.append({
            "id": s.id,
            "date": s.slot_date.isoformat(),
            "title": s.title,
            "capacity": s.capacity,
            "status": s.status,
            "enrolled": len(users),
            "available": max(s.capacity - len(users), 0),
            "users": users,
        })

    return render(request, "app/hours.html", {"hours": data,
                                                "prev_date": prev_day.isoformat(),
                                                "next_date": next_day.isoformat(), 
                                                "date": format_es_date(day)})



def edit(request):
    raw = request.GET.get("userid")
    user = None
    if raw:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("userid inválido")
        user = get_object_or_404(GymUser, pk=user_id)

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            if not user:
                return HttpResponseBadRequest("No puedes borrar: usuario no encontrado")
            user.delete()
            return redirect("app.users")

        first_name = (request.POST.get("first_name") or "").strip()
        last_name  = (request.POST.get("last_name") or "").strip()
        full_name  = (first_name + " " + last_name).strip() or "Sin nombre"

        phone      = (request.POST.get("phone") or "").strip() or None
        birth_date = parse_date(request.POST.get("birth_date") or "")
        join_date = parse_date(request.POST.get("join_date") or "")
        height_cm  = request.POST.get("height_cm")

        if user is None:
            user = GymUser.objects.create(
                full_name=full_name,
                role="member",
                join_date=join_date,
                birth_date=birth_date,
                phone=phone,
                height_cm=height_cm or None,
            )
        else:
            user.full_name = full_name
            user.birth_date = birth_date
            user.phone = phone
            user.join_date = join_date
            user.height_cm = height_cm or None
            user.save(update_fields=["full_name", "birth_date", "phone", "join_date", "height_cm", "updated_at"])

        User = get_user_model()
        username = str(user.id)
        if not User.objects.filter(username=username).exists():
            auth_u = User(username=username, first_name=first_name, last_name=last_name)
            auth_u.set_password("gim12345")
            auth_u.save()

        base_url = reverse("app.profile")                 # -> "/profile/"
        query = urlencode({"userid": user.id})            # -> "userid=123"
        return redirect(f"{base_url}?{query}") 

    ctx = {
        "is_edit": bool(user),
        "userid": user.id if user else None,
        "full_name": user.full_name if user else None,
        "first_name": (user.full_name.split(" ", 1)[0] if user else ""),
        "last_name":  (user.full_name.split(" ", 1)[1] if (user and " " in user.full_name) else ""),
        "phone": user.phone if user else "",
        "birth_date": user.birth_date.isoformat() if (user and user.birth_date) else "",
        "join_date": user.join_date.isoformat() if (user and user.join_date) else timezone.localdate().isoformat(),
        "height_cm": user.height_cm if user else None,
    }
    return render(request, "app/editprofile.html", ctx)

METHOD_CHOICES = [
    ("efectivo", "Efectivo"),
    ("transferencia", "Transferencia"),
    ("sinpe", "SINPE"),
]

MONTHS_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def _clamp_dom(y: int, m: int, dom: int) -> date:
    return date(y, m, min(dom, monthrange(y, m)[1]))

def _period_bounds_by_anchor(year: int, month: int, anchor_day: int) -> tuple[date, date]:
    """
    Devuelve (period_start, period_end_exclusive) anclado al día 'anchor_day'.
    'month' es 1..12 y 'year' completo.
    """
    ps = _clamp_dom(year, month, anchor_day)
    # siguiente mes:
    ny = year + (1 if month == 12 else 0)
    nm = 1 if month == 12 else month + 1
    pe = _clamp_dom(ny, nm, anchor_day)  # exclusivo
    return ps, pe

def _period_label(year: int, month: int) -> str:
    return f"{MONTHS_ES[month-1]} {year}"

def _parse_amount(raw: str) -> int:
    """Quita separadores y devuelve entero en unidades (colones)."""
    if not raw:
        return 0
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits or 0)

def _period_options(n: int = 6) -> list[tuple[str, str]]:
    """Meses desde el actual hacia adelante: value='YYYY-MM', label='Mes-YYYY'."""
    today = timezone.localdate()
    y, m = today.year, today.month
    out = []
    for i in range(n):
        yy = y + (m + i - 1) // 12
        mm = (m + i - 1) % 12 + 1
        out.append((f"{yy:04d}-{mm:02d}", _period_label(yy, mm)))
    return out


def payment(request):
    """
    GET:
      - Nuevo: /pago/
      - Editar: /pago/?paymentid=<id>
    POST:
      - Crea o actualiza y redirige a home (si edit, añade ?pagoid=)
    """
    pagoid = request.GET.get("paymentid") or request.POST.get("paymentid")
    pref_user_id = request.GET.get("userid") or request.POST.get("userid")

    is_edit = bool(pagoid)

    payment = None
    if is_edit:
        payment = get_object_or_404(Payment, pk=pagoid)

    if request.method == "POST":
        # --- leer form ---
        user_id   = request.POST.get("user")
        amount_in = request.POST.get("amount")
        method    = request.POST.get("method") or ""
        paid_at_s = request.POST.get("paid_at")  # YYYY-MM-DD
        period_v  = request.POST.get("period")   # "YYYY-MM"
        notes     = request.POST.get("notes") or ""

        # Validaciones mínimas (frontend hará la UX)
        if not user_id or not period_v or not paid_at_s or not method:
            # Re-render simple con error
            ctx = _pago_context(is_edit, pagoid, payment, pref_user_id)
            ctx.update({"error": "Faltan campos obligatorios.",})
            return render(request, "app/payment.html", ctx)

        user = get_object_or_404(GymUser, pk=user_id)
        amount = _parse_amount(amount_in)
        # paid_at como date (tu diseño solo trae date; si usas datetime, ajústalo)
        try:
            y, m, d = map(int, paid_at_s.split("-"))
            paid_at = date(y, m, d)
        except Exception:
            ctx = _pago_context(is_edit, pagoid, payment)
            ctx.update({"error": "Fecha de pago inválida."})
            return render(request, "app/payment.html", ctx)

        # periodo (YYYY-MM) -> bounds y label
        try:
            py, pm = map(int, period_v.split("-"))
        except Exception:
            ctx = _pago_context(is_edit, pagoid, payment)
            ctx.update({"error": "Periodo inválido."})
            return render(request, "app/payment.html", ctx)

        # Ancla por día de alta del usuario (si no tiene, usa día 1)
        anchor_day = user.join_date.day if getattr(user, "join_date", None) else 1
        period_start, period_end = _period_bounds_by_anchor(py, pm, anchor_day)
        period_label = _period_label(py, pm)

        # --- guardar ---
        if is_edit:
            p = payment
            p.user = user
            p.amount = amount
            p.method = method
            p.paid_at = paid_at
            p.period_start = period_start
            p.period_end = period_end
            p.period_label = period_label
            p.notes = notes
            p.save()
            if pref_user_id:
                return redirect(f"{reverse('app.payments')}?userid={pref_user_id}")
            else:
                return redirect("app.home")
        else:
            p = Payment.objects.create(
                user=user,
                amount=amount,
                method=method,
                paid_at=paid_at,
                period_start=period_start,
                period_end=period_end,
                period_label=period_label,
                notes=notes,
            )
            if pref_user_id:
                return redirect(f"{reverse('app.payments')}?userid={pref_user_id}")
            else:
                return redirect("app.home")

    # GET
    ctx = _pago_context(is_edit, pagoid, payment, pref_user_id)
    return render(request, "app/payment.html", ctx)


def _pago_context(is_edit: bool, pagoid: str | None, payment: Payment | None, pref_user_id: str | None = None):
    """Contexto común para el template."""
    users = GymUser.objects.filter(is_active=True).only("id", "full_name").order_by("full_name")
    methods = METHOD_CHOICES
    periods = _period_options(2)

    initial = {}
    if payment:
        # Prellenar para edición (periodo en YYYY-MM)
        ps = payment.period_start
        initial = {
            "user_id": payment.user_id,
            "amount": payment.amount,
            "method": payment.method,
            "paid_at": payment.paid_at.date().isoformat() if hasattr(payment.paid_at, "isoformat") else "",
            "period": f"{ps.year:04d}-{ps.month:02d}",
            "notes": payment.notes or "",
        }
    else:                                 # ← NUEVO
        try:
            if pref_user_id:
                initial["user_id"] = int(pref_user_id)
                initial["paid_at"] = timezone.localdate().isoformat() 
        except ValueError:
            pass

    return {
        "is_edit": is_edit,
        "user_id": pref_user_id,
        "payment_id": pagoid,
        "users": users,
        "methods": methods,
        "periods": periods,
        "initial": initial,
    }

def payments(request):
    """
    /pagos/?filter=all
             |period&period=YYYY-MM
             |last_3
             |last_7
             [&userid=<id>]

    - all          : todos los pagos (por defecto)
    - period       : pagos cuyo periodo (period_start) coincide con YYYY-MM
    - last_3       : pagos en los últimos 3 días (incluye hoy)
    - last_7       : pagos en los últimos 7 días (incluye hoy)
    - userid       : limita a los pagos de ese usuario

    Context -> {"payments": [{"full_name", "paid_at_label"}], "filter": <str>}
    """
    filt = (request.GET.get("filter") or "all").strip().lower()
    userid = request.GET.get("userid")
    period_str = request.GET.get("period")  # "YYYY-MM" cuando filter=period

    today = timezone.localdate()

    # Base queryset
    qs = (
        Payment.objects
        .select_related("user")
        .only("id", "paid_at", "period_start", "period_end", "period_label", "method", "amount", "user__id", "user__full_name")
    )

    if userid:
        try:
            uid = int(userid)
            qs = qs.filter(user_id=uid)
        except (TypeError, ValueError):
            pass  # si viene mal, simplemente no filtra por usuario

    if filt == "period" and period_str:
        try:
            y, m = map(int, period_str.split("-"))
            qs = qs.filter(period_start__year=y, period_start__month=m)
        except Exception:
            # si el periodo viene mal, no aplica filtro adicional
            pass
    elif filt == "last_3":
        since = today - timedelta(days=3)
        qs = qs.filter(paid_at__date__gte=since)
    elif filt == "last_7":
        since = today - timedelta(days=7)
        qs = qs.filter(paid_at__date__gte=since)
    else:
        # "all" u otros -> sin filtro extra
        pass

    qs = qs.order_by("-paid_at", "-id")

    # Adaptamos al formato que tu template espera:
    #   <span class="text-base font-medium">{{ full_name }}</span>
    #   <span class="text-xs text-gray-500">{{ paid_at_label }}</span>
    out = []
    for p in qs:
        full_name = p.user.full_name if p.user_id else "—"
        paid_date = p.paid_at.date() if hasattr(p.paid_at, "date") else p.paid_at
        out.append({
            "id": p.id,
            "full_name": full_name,
            "paid_at_label": format_es_date(paid_date, include_year=True),
            "period_label": p.period_label,
            "method": p.get_method_display(),
            "amount": p.amount,

        })

    return render(request, "app/payments.html", {
        "payments": out,
        "filter": filt,
        "period": period_str or "",
        "user_id": userid or "",
    })

# app/views.py
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse_lazy

# --- Custom Auth Form: solo para renombrar el label de username ---
class MemberLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Renombra el campo username para que se vea como "Número de miembro"
        self.fields["username"].label = "Número de miembro"
        self.fields["username"].widget.attrs.update({
            "placeholder": "Tu número de miembro",
            "autocomplete": "username",
        })
        self.fields["password"].widget.attrs.update({
            "placeholder": "Contraseña",
            "autocomplete": "current-password",
        })

# --- Login ---
class AppLoginView(LoginView):
    template_name = "app/login.html"
    authentication_form = MemberLoginForm
    redirect_authenticated_user = True

    # Mantén sesión abierta N días desde settings; si quieres forzarlo aquí:
    def form_valid(self, form):
        response = super().form_valid(form)
        # Si quisieras un valor distinto al global:
        # self.request.session.set_expiry(60 * 60 * 24 * 21)
        return response

# --- Logout ---
def logout_view(request):
    logout(request)
    return redirect("app.login")

# --- Cambio de contraseña ---
class MemberPasswordChangeView(PasswordChangeView):
    template_name = "app/password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("app.home")  # vuelve al home después de cambiar
