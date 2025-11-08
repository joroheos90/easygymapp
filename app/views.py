# Standard library
from calendar import monthrange
from datetime import date, timedelta
from urllib.parse import urlencode

# Third-party
from dateutil.relativedelta import relativedelta

# Django
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

# Local
from app.services import GymService
from .helpers import format_es_date, gym_required, role_required, signed_at_parts
from .models import BaseTimeslot, DailyTimeslot, Gym, GymUser, Payment, TimeslotSignup


@login_required
@require_http_methods(["GET", "POST"])
@role_required(["admin", "member"])
def home(request):
    gp = request.gym_user

    if request.method == "POST":
        posted_gym_id = request.POST.get("gym_id")

        if request.is_admin:
            # Admin puede seleccionar cualquier gym activo
            gym = get_object_or_404(Gym, pk=posted_gym_id, is_active=True)
        else:
            # Member: fuerza su propio gym (aunque postee otro id)
            if getattr(gp, "gym_id", None):
                gym = get_object_or_404(Gym, pk=gp.gym_id, is_active=True)
            else:
                # Sin gym en el perfil: no puede seleccionar otro
                return redirect("app.home")

        # Persistir selección
        request.session["gym_id"] = str(gym.id)

        # Redirigir según rol
        if request.is_admin:
            return redirect("app.admin")
        else:
            if gp and gp.id:
                profile_url = reverse("app.profile")
                return redirect(f"{profile_url}?userid={gp.id}")
            return redirect("app.home")

    # GET: lista de gyms según rol
    if request.is_admin:
        gyms = Gym.objects.filter(is_active=True).only("id", "name", "address").order_by("name")
    else:
        # Solo el gym del miembro (si tiene)
        if getattr(gp, "gym_id", None):
            gyms = Gym.objects.filter(id=gp.gym_id, is_active=True).only("id", "name", "address")
        else:
            gyms = Gym.objects.none()

    selected_id = getattr(getattr(request, "gym", None), "id", None)
    return render(request, "app/home.html", {"gyms": gyms, "selected_gym_id": selected_id})


@login_required
@role_required(["admin"])
@gym_required
def admin(request):
    today = timezone.localdate()

    active_members = GymUser.objects.filter(gym=request.gym, is_active=True, role="member").count()

    qs = Payment.objects.all()
    qs = qs.filter(gym=request.gym, period_start__lte=today, period_end__gt=today)

    period_income = qs.aggregate(total=Sum("amount"))["total"] or 0

    ctx = {
        "active_members": active_members,
        "period_income": period_income,
        "period_label": _period_label(today.year, today.month),
        "gym_name": request.gym.name
    }
    return render(request, "app/admin.html", ctx)


from datetime import timedelta, date
from django.contrib import messages
# ...

@login_required
@role_required(["admin"])
@require_http_methods(["GET", "POST"])
@gym_required
def base_hours(request):
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)

    AVOID_WEEKDAYS = {5, 6}

    def can_publish(day: date) -> bool:
        return day.weekday() not in AVOID_WEEKDAYS

    def publish_for_day(day: date) -> tuple[int, int]:
        """Crea DailyTimeslot desde BaseTimeslot para un día. Devuelve (created, skipped)."""
        if not can_publish(day):
            return (0, 0)

        created = skipped = 0
        base_qs = (
            BaseTimeslot.objects
            .only("id", "title", "capacity", "is_active")
            .order_by("id")
            .filter(gym=request.gym, is_active=True)
        )
        for b in base_qs:
            obj, made = DailyTimeslot.objects.get_or_create(
                gym=request.gym,
                base=b,
                slot_date=day,
                defaults={
                    "title": b.title,
                    "capacity": b.capacity,
                    "status": DailyTimeslot.Status.OPEN,
                },
            )
            if made:
                created += 1
            else:
                skipped += 1
        return created, skipped

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        created_total = skipped_total = 0
        avoided_days = 0

        with transaction.atomic():
            if action == "today":
                if can_publish(today):
                    c, s = publish_for_day(today)
                    created_total += c; skipped_total += s
                else:
                    avoided_days += 1
            elif action == "tomorrow":
                if can_publish(tomorrow):
                    c, s = publish_for_day(tomorrow)
                    created_total += c; skipped_total += s
                else:
                    avoided_days += 1
            elif action == "week":
                for i in range(0, 7):
                    day = today + timedelta(days=i)
                    if not can_publish(day):
                        avoided_days += 1
                        continue
                    c, s = publish_for_day(day)
                    created_total += c; skipped_total += s
        return redirect("app.base_hours")

    # GET
    qs = (
        BaseTimeslot.objects
        .filter(gym=request.gym)
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

    # Flags para hoy/mañana (si son fin de semana, márcalos como ya “no publicables”)
    exists_today = DailyTimeslot.objects.filter(gym=request.gym, slot_date=today).exists()
    exists_tomorrow = DailyTimeslot.objects.filter(gym=request.gym, slot_date=tomorrow).exists()

    # Semana: contar solo días publicables que falten
    week_days = [today + timedelta(days=i) for i in range(0, 7)]
    week_missing = [
        d for d in week_days
        if can_publish(d) and not DailyTimeslot.objects.filter(gym=request.gym, slot_date=d).exists()
    ]
    week_missing_count = len(week_missing)

    ctx = {
        "hours": hours,
        "today": today,
        "tomorrow": tomorrow,
        "already_created_for_today": exists_today or not can_publish(today),
        "already_created_for_tomorrow": exists_tomorrow or not can_publish(tomorrow),
        "week_missing_count": week_missing_count,
        "avoid_weekdays": sorted(AVOID_WEEKDAYS),  # opcional por si lo quieres mostrar
    }
    return render(request, "app/base_hours.html", ctx)


@login_required
@role_required(["member"])
@require_http_methods(["GET", "POST"])
@gym_required
def selector(request):
    q = request.GET.get("date") or request.POST.get("date")
    day = parse_date(q) if q else None
    if day is None:
        day = timezone.localdate()

    error = None
    success = None

    if request.method == "POST":
        slot_id_raw = request.POST.get("slot_id")
        try:
            slot_id = int(slot_id_raw)
        except (TypeError, ValueError):
            slot_id = None

        if not slot_id:
            error = "Horario inválido."
        else:
            slot = get_object_or_404(DailyTimeslot, pk=slot_id)

            if slot.slot_date != day:
                day = slot.slot_date

            with transaction.atomic():
                existing = (
                    TimeslotSignup.objects
                    .select_for_update()
                    .filter(gym=request.gym, user=request.gym_user, slot_date=day)
                    .first()
                )

                if existing and existing.daily_slot_id == slot.id:
                    # Seleccionó el mismo -> CANCELAR su participación
                    existing.delete()
                    success = f"Se canceló tu registro con éxito"
                else:
                    # Cambiar (o crear) inscripción -> validar pago y cupo
                    ps, pe = _current_period_for(request.gym_user, ref=timezone.localdate())
                    has_paid = Payment.objects.filter(
                        gym=request.gym, user=request.gym_user, period_start__lte=ps, period_end__gte=pe
                    ).exists()
                    if not has_paid:
                        error = "Debes tener tu pago al día para inscribirte."
                    else:
                        # Cupo del destino
                        enrolled = TimeslotSignup.objects.filter(daily_slot=slot).count()
                        cap = slot.capacity or 0
                        if enrolled >= cap:
                            error = "Este horario ya está lleno."
                        else:
                            # Si estaba inscrito en otro horario del mismo día, borra primero
                            if existing:
                                existing.delete()
                            # Crea la nueva inscripción
                            TimeslotSignup.objects.create(
                                gym=request.gym,
                                daily_slot=slot,
                                user=request.gym_user,
                                slot_date=slot.slot_date,   # NOT NULL
                                signed_at=timezone.now(),
                            )
                            success = f"Registro completado con éxito."

        if error:
            messages.error(request, error)
        elif success:
            messages.success(request, success)
        return redirect(f"{reverse('app.selector')}?date={day.isoformat()}")

    # Cargar data para la UI (siempre)
    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    my_slot_ids = set()
    my_slot_ids = set(
        TimeslotSignup.objects
        .filter(gym=request.gym, user=request.gym_user, slot_date=day)
        .values_list("daily_slot_id", flat=True)
    )

    slots = (
        DailyTimeslot.objects
        .filter(gym=request.gym, slot_date=day)
        .annotate(enrolled=Count("signups"))
        .order_by("id")
        .only("id", "slot_date", "title", "capacity", "status")
    )

    hours = []
    for s in slots:
        cap = s.capacity or 0
        enrolled = int(s.enrolled or 0)
        pct = int(round((enrolled / cap) * 100)) if cap > 0 else 0
        if pct > 100: pct = 100
        hours.append({
            "id": s.id,
            "title": s.title,
            "capacity": cap,
            "enrolled": enrolled,
            "available": max(cap - enrolled, 0),
            "status": s.status,
            "occupancy_pct": pct,
            "occupancy_width": f"{pct}%",
            "is_mine": (s.id in my_slot_ids), 
        })

    ctx = {
        "hours": hours,
        "date": format_es_date(day, include_year=False, include_weekday=True),
        "raw_date": day.isoformat(),
        "prev_date": prev_day.isoformat(),
        "next_date": next_day.isoformat(),
        "error": error,
        "success": success,
    }
    return render(request, "app/hourselection.html", ctx)




def _current_period_for(user: GymUser, ref: date | None = None) -> tuple[date, date]:
    today = ref or timezone.localdate()
    anchor = user.join_date.day
    if today.day < anchor:
        start = (today.replace(day=1) - relativedelta(months=1)).replace(day=anchor)
    else:
        start = today.replace(day=anchor)
    end = start + relativedelta(months=1)  # exclusivo
    return start, end

@login_required
@role_required(["admin"])
@gym_required
def users(request):
    filt = (request.GET.get("filter") or "all").strip().lower()
    delinquent_days = int(request.GET.get("days") or 30)
    today = timezone.localdate()
    qs = (
        GymUser.objects
        .filter(gym=request.gym, is_active=True, role="member")
        .only("id", "full_name", "join_date")
        .order_by("full_name")
    )

    out = []
    for u in qs:
        ps, pe = _current_period_for(u, ref=today)
        paid = Payment.objects.filter(gym=request.gym,
            user=u, period_start__lte=ps, period_end__gte=pe
        ).exists()

        agg = Payment.objects.filter(gym=request.gym, user=u).aggregate(last_end=Max("period_end"))
        last_end = agg["last_end"]
        if last_end:
            last_covered_day = last_end - timedelta(days=1)
            days_since_last_cover = (today - last_covered_day).days
        else:
            days_since_last_cover = 10**9
            
        if not paid:
            if agg["last_end"]:
                expired_on = agg["last_end"]
            else:
                expired_on = ps
        else:
            expired_on = None



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
                "expired_on": format_es_date(expired_on) if expired_on else "",
            })

    return render(request, "app/users.html", {"users": out, "filter": filt})


@login_required
@gym_required
@role_required(["admin", "member"])
def profile(request):
    if request.is_member:
        raw = request.user_id
    else:
        raw = request.GET.get("userid")
    if not raw:
        return HttpResponseBadRequest("Falta el parámetro ?userid")

    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("userid inválido")

    user = get_object_or_404(
        GymUser.objects.filter(gym=request.gym).prefetch_related(
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
        gym=request.gym, user=user, period_start__lte=ps, period_end__gte=pe
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

    expired_on = None
    if not has_paid:
        if last_payment:
            expired_on = last_payment.period_end
        else:
            expired_on = ps

    ctx = {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "phone": getattr(user, "phone", None),
            "expired_on": format_es_date(expired_on, include_year=True) if expired_on else "",
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

@login_required
@role_required(["admin"])
@gym_required
def hours(request):
    q = request.GET.get("date")
    day = parse_date(q) if q else None
    if day is None:
        day = timezone.localdate()

    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    slots = (
        DailyTimeslot.objects
        .filter(gym=request.gym, slot_date=day)
        .order_by("id")
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
                                                "date": format_es_date(day, include_weekday=True)})

@login_required
@role_required(["member", "admin"])
@gym_required
def user(request):
    if request.is_member:
        raw = request.user_id
    else:
        raw = request.GET.get("userid")
    member = None
    if raw:
        try:
            member_id = int(raw)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("userid inválido")
        member = get_object_or_404(GymUser, pk=member_id)

    if not request.is_admin:
        if member is None:
            return redirect("app.home")
        if member.id != request.user_id:
            return redirect("app.home")


    if request.method == "POST":
        if request.POST.get("action") == "delete":
            if not member:
                return HttpResponseBadRequest("No puedes borrar: usuario no encontrado")
            # borra GymUser (OneToOne con on_delete=CASCADE borrará también el auth.User)
            member.delete()
            return redirect("app.users")

        # ---- datos del form ----
        first_name = (request.POST.get("first_name") or "").strip()
        last_name  = (request.POST.get("last_name") or "").strip()
        full_name  = (first_name + " " + last_name).strip() or "Sin nombre"

        phone      = (request.POST.get("phone") or "").strip() or None
        birth_date = parse_date(request.POST.get("birth_date") or "")
        join_date  = parse_date(request.POST.get("join_date") or "") or timezone.localdate()
        height_cm  = request.POST.get("height_cm") or None
        is_active  = True  # si agregas toggle en UI, léelo aquí

        if member is None:
            # Crear GymUser + auth.User (OneToOne) con password por defecto
            member, auth_u = GymService.crear_gymuser_y_user(gym=request.gym, full_name=full_name, is_active=is_active, password="gim12345")
            # Completar/ajustar campos del perfil recién creado
            member.phone = phone
            member.birth_date = birth_date
            member.join_date = join_date
            member.height_cm = height_cm
            member.save(update_fields=["phone", "birth_date", "join_date", "height_cm", "updated_at", "gym_id"])
        else:
            # Update GymUser
            member.full_name  = full_name
            member.phone      = phone
            member.birth_date = birth_date
            member.join_date  = join_date
            member.height_cm  = height_cm
            member.is_active  = is_active
            member.save(update_fields=["full_name", "phone", "birth_date", "join_date", "height_cm", "is_active", "updated_at"])

            # Sync con auth.User si está enlazado
            if member.user_id:
                au = member.user
                # separar nombres
                fn = first_name
                ln = last_name
                updates = []
                if au.first_name != fn:
                    au.first_name = fn; updates.append("first_name")
                if au.last_name != ln:
                    au.last_name = ln; updates.append("last_name")
                if au.is_active != member.is_active:
                    au.is_active = member.is_active; updates.append("is_active")
                if updates:
                    au.save(update_fields=updates)

        # redirect a perfil
        base_url = reverse("app.profile")
        query = urlencode({"userid": member.id})
        return redirect(f"{base_url}?{query}")

    # ---- GET: pintar formulario ----
    ctx = {
        "is_edit": bool(member),
        "userid": member.id if member else None,
        "full_name": member.full_name if member else None,
        "first_name": (member.full_name.split(" ", 1)[0] if member else ""),
        "last_name":  (member.full_name.split(" ", 1)[1] if (member and " " in member.full_name) else ""),
        "phone": member.phone if member else "",
        "birth_date": member.birth_date.isoformat() if (member and member.birth_date) else "",
        "join_date": member.join_date.isoformat() if (member and member.join_date) else timezone.localdate().isoformat(),
        "height_cm": member.height_cm if member else None,
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
    date = timezone.localdate()
    today = date - timedelta(weeks=8)
    y, m = today.year, today.month
    out = []
    for i in range(n):
        yy = y + (m + i - 1) // 12
        mm = (m + i - 1) % 12 + 1
        out.append((f"{yy:04d}-{mm:02d}", _period_label(yy, mm)))
    return out


@login_required
@role_required(["admin"])
@gym_required
def payment(request):
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
            ctx = _pago_context(request.gym, is_edit, pagoid, payment, pref_user_id)
            ctx.update({"error": "Faltan campos obligatorios.",})
            return render(request, "app/payment.html", ctx)

        user = get_object_or_404(GymUser, pk=user_id)
        amount = _parse_amount(amount_in)
        # paid_at como date (tu diseño solo trae date; si usas datetime, ajústalo)
        try:
            y, m, d = map(int, paid_at_s.split("-"))
            paid_at = date(y, m, d)
        except Exception:
            ctx = _pago_context(request.gym, is_edit, pagoid, payment)
            ctx.update({"error": "Fecha de pago inválida."})
            return render(request, "app/payment.html", ctx)

        # periodo (YYYY-MM) -> bounds y label
        try:
            py, pm = map(int, period_v.split("-"))
        except Exception:
            ctx = _pago_context(request.gym, is_edit, pagoid, payment)
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
            if pref_user_id and pagoid:
                return redirect(f"{reverse('app.profile')}?userid={pref_user_id}")
            elif pref_user_id:
                return redirect(f"{reverse('app.payments')}?userid={pref_user_id}")
            else:
                return redirect("app.payments")
        else:
            p = Payment.objects.create(
                gym=request.gym,
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
                return redirect("app.payments")

    # GET
    ctx = _pago_context(request.gym, is_edit, pagoid, payment, pref_user_id)
    return render(request, "app/payment.html", ctx)


def _pago_context(gym, is_edit: bool, pagoid: str | None, payment: Payment | None, pref_user_id: str | None = None):
    """Contexto común para el template."""
    users = GymUser.objects.filter(gym=gym, is_active=True).only("id", "full_name").order_by("full_name")
    methods = METHOD_CHOICES
    periods = _period_options(4)

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


@login_required
@role_required(["member", "admin"])
@gym_required
def payments(request):
    gp = getattr(request, "gym_user", None)
    is_member = getattr(gp, "role", "") == "member"

    if is_member:
        userid = gp.id
    else:
        raw = request.GET.get("userid")
        try:
            userid = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            userid = None

    filt = (request.GET.get("filter") or "all").strip().lower()
    # Acepta alias comunes
    if filt in {"hoy"}:
        filt = "today"
    if filt in {"ultimos_3", "3"}:
        filt = "last_3"
    if filt in {"ultimos_7", "7"}:
        filt = "last_7"
    if filt in {"mes", "month_current"}:
        filt = "month"

    today = timezone.localdate()

    qs = (
        Payment.objects
        .filter(gym=request.gym)
        .select_related("user")
        .only(
            "id", "paid_at", "amount", "method",
            "period_label", "user__id", "user__full_name"
        )
    )

    if userid:
        # Garantiza que el user pertenezca al mismo gym (seguridad)
        get_object_or_404(GymUser, id=userid, gym=request.gym)
        qs = qs.filter(user_id=userid)

    # Aplica rango por fecha de pago (paid_at__date)
    if filt == "today":
        qs = qs.filter(paid_at__date=today)
    elif filt == "last_3":
        since = today - timedelta(days=3)
        qs = qs.filter(paid_at__date__gte=since)
    elif filt == "last_7":
        since = today - timedelta(days=7)
        qs = qs.filter(paid_at__date__gte=since)
    elif filt == "month":
        qs = qs.filter(paid_at__year=today.year, paid_at__month=today.month)
    # "all" -> sin filtro extra

    qs = qs.order_by("-paid_at", "-id")

    # Adaptar al template (nombre y fecha en español)
    out = []
    for p in qs:
        paid_date = p.paid_at.date() if hasattr(p.paid_at, "date") else p.paid_at
        out.append({
            "id": p.id,
            "full_name": p.user.full_name if p.user_id else "—",
            "paid_at_label": format_es_date(paid_date, include_year=True),
            "period_label": p.period_label,
            "method": p.get_method_display(),  # “Efectivo / Transferencia / SINPE”
            "amount": p.amount,
        })

    return render(request, "app/payments.html", {
        "payments": out,
        "filter": filt,
        "user_id": userid or "",
    })

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
