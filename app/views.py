from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from .helpers import (
    signed_at_parts,
    format_es_date,
)
from django.urls import reverse
from urllib.parse import urlencode
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponseBadRequest
from app.models import GymUser
from datetime import date
from .models import DailyTimeslot, GymUser, UserWeight

def index(request):
    return render(request, "app/home.html")


def selector(request):
    return render(request, "app/hourselection.html")


def _amount_from_cents(cents: int | None) -> float:
    return (cents or 0) / 100.0

def profile(request):
    """
    /profile/?userid=2323
    Lee el ID desde el querystring (?userid=...) y renderiza el perfil completo.
    """
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

    ctx = {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "phone": getattr(user, "phone", None),
            "join_date": format_es_date(user.join_date),
            "birth_date": format_es_date(user.birth_date),
            "is_active": user.is_active,
            "weight": weight,
        }
    }
    return render(request, "app/profile.html", ctx)



def hours(request):
    q = request.GET.get("date")
    day = parse_date(q) if q else None
    if day is None:
        day = timezone.localdate()

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

    return render(request, "app/hours.html", {"hours": data, "date": format_es_date(day)})



def edit(request):
    """
    Crea o actualiza un usuario:
      - GET  /profile/edit/?userid=123   -> edita
      - GET  /profile/edit/              -> nuevo
      - POST /profile/edit/?userid=123   -> guarda edición
      - POST /profile/edit/              -> guarda nuevo
      - POST con action=delete y userid  -> borra
    """
    raw = request.GET.get("userid")
    user = None
    if raw:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("userid inválido")
        user = get_object_or_404(GymUser, pk=user_id)

    if request.method == "POST":
        # ¿Borrar?
        if request.POST.get("action") == "delete":
            if not user:
                return HttpResponseBadRequest("No puedes borrar: usuario no encontrado")
            user.delete()
            return redirect("app.profile")  # ajusta a donde quieras volver

        # Crear/actualizar
        first_name = (request.POST.get("first_name") or "").strip()
        last_name  = (request.POST.get("last_name") or "").strip()
        full_name  = (first_name + " " + last_name).strip() or "Sin nombre"

        phone      = (request.POST.get("phone") or "").strip() or None
        birth_date = parse_date(request.POST.get("birth_date") or "")  # None si vacío

        # Opcionales de estatura y peso
        height_cm  = request.POST.get("height_cm")  # si tienes campo height_cm en el modelo
        weight_kg  = request.POST.get("weight_kg")

        if user is None:
            # Nuevo
            user = GymUser.objects.create(
                full_name=full_name,
                role="member",
                join_date=date.today(),
                birth_date=birth_date,
                phone=phone,
                # si agregaste height_cm en tu modelo, descomenta:
                # height_cm=height_cm or None,
            )
        else:
            # Update
            user.full_name = full_name
            user.birth_date = birth_date
            user.phone = phone
            # si agregaste height_cm:
            # user.height_cm = height_cm or None
            user.save(update_fields=["full_name", "birth_date", "phone", "updated_at"])

        # Si viene peso, guarda registro de peso más reciente
        try:
            if weight_kg:
                val = float(weight_kg)
                if val > 0:
                    UserWeight.objects.create(
                        user=user,
                        weight_kg=val,
                        recorded_at=timezone.now(),
                    )
        except ValueError:
            pass  # si no es número, lo ignoramos (validas en front)

        base_url = reverse("app.profile")                 # -> "/profile/"
        query = urlencode({"userid": user.id})            # -> "userid=123"
        return redirect(f"{base_url}?{query}") 

    # GET: render form con valores iniciales
    ctx = {
        "is_edit": bool(user),
        "userid": user.id if user else None,
        "first_name": (user.full_name.split(" ", 1)[0] if user else ""),
        "last_name":  (user.full_name.split(" ", 1)[1] if (user and " " in user.full_name) else ""),
        "phone": user.phone if user else "",
        "birth_date": user.birth_date.isoformat() if (user and user.birth_date) else "",
        # Si usas height_cm en el modelo:
        # "height_cm": user.height_cm or "",
    }
    return render(request, "app/editprofile.html", ctx)
