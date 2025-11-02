# app/migrations/0003_seed_demo_data.py
from django.db import migrations
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import random


def current_period_for(join_date: date, ref: date) -> tuple[date, date]:
    """
    Periodo mensual anclado al día de join_date; end exclusivo.
    """
    base_day = join_date.day
    if ref.day < base_day:
        start = (ref.replace(day=1) - relativedelta(months=1)).replace(day=base_day)
    else:
        start = ref.replace(day=base_day)
    end = start + relativedelta(months=1)
    return start, end


def seed(apps, schema_editor):
    # IMPORTANTE: app label = "app"
    GymUser = apps.get_model("app", "GymUser")
    BaseTimeslot = apps.get_model("app", "BaseTimeslot")
    DailyTimeslot = apps.get_model("app", "DailyTimeslot")
    TimeslotSignup = apps.get_model("app", "TimeslotSignup")
    UserWeight = apps.get_model("app", "UserWeight")
    Payment = apps.get_model("app", "Payment")

    rng = random.Random(42)
    now = timezone.now()
    today = timezone.localdate()

    # 1) Usuarios DEMO (idempotente por nombre)
    demo_names = [
        "Juan Pérez", "María López", "Carlos Gómez", "Ana Rodríguez", "Luis Hernández",
        "Sofía Martínez", "Jorge Sánchez", "Valeria Torres", "Diego Ramírez", "Paula Cruz",
    ]
    demo_users = []
    for i, name in enumerate(demo_names):
        full_name = f"[DEMO] {name}"
        user, created = GymUser.objects.get_or_create(
            full_name=full_name,
            defaults={
                "role": "admin" if i == 0 else "member",
                "join_date": today - relativedelta(months=rng.randint(1, 10)),
                "birth_date": date(1990 + rng.randint(0, 10), rng.randint(1, 12), rng.randint(1, 28)),
                "is_active": True,
                "created_at": now,
            },
        )
        demo_users.append(user)

    # 2) Horarios base (si no existen)
    base_specs = [
        ("6 am a 7 am", 15),
        ("7 am a 8 am", 15),
        ("8 am a 9 am", 15),
        ("6 pm a 7 pm", 20),
        ("7 pm a 8 pm", 20),
    ]
    base_objs = []
    for title, cap in base_specs:
        base, _ = BaseTimeslot.objects.get_or_create(
            title=title,
            defaults={"capacity": cap, "is_active": True, "created_at": now, "updated_at": now},
        )
        base_objs.append(base)

    # 3) Horarios diarios para HOY (idempotente por (date, title))
    daily_slots = []
    for base in base_objs:
        ds, _ = DailyTimeslot.objects.get_or_create(
            slot_date=today,
            title=base.title,
            defaults={
                "base_id": base.id,
                "capacity": base.capacity,
                "status": "open",
                "created_at": now,
            },
        )
        daily_slots.append(ds)

    # 4) Inscribir usuarios aleatoriamente (1 horario por día por usuario si existe la UNIQUE)
    TimeslotSignup.objects.filter(slot_date=today, user__full_name__startswith="[DEMO] ").delete()

    remaining = {ds.id: ds.capacity for ds in daily_slots}
    rng.shuffle(demo_users)

    for user in demo_users:
        attempts = 5
        while attempts > 0:
            ds = rng.choice(daily_slots)
            if remaining[ds.id] > 0 and ds.status == "open":
                try:
                    TimeslotSignup.objects.create(
                        daily_slot_id=ds.id,
                        user_id=user.id,
                        signed_at=now,
                        slot_date=today,
                    )
                    remaining[ds.id] -= 1
                    break
                except Exception:
                    # Puede fallar por UNIQUE (user, slot_date) o (daily_slot, user)
                    pass
            attempts -= 1

    # 5) Historial de peso: un registro por usuario DEMO
    for u in demo_users:
        if not UserWeight.objects.filter(user_id=u.id).exists():
            UserWeight.objects.create(
                user_id=u.id,
                weight_kg=round(rng.uniform(55, 95), 1),
                recorded_at=now - timedelta(days=rng.randint(0, 14)),
            )

    # 6) Algunos pagos en el periodo actual (para ~la mitad)
    for u in demo_users[::2]:
        ps, pe = current_period_for(u.join_date, today)
        exists = Payment.objects.filter(
            user_id=u.id, period_start__lte=ps, period_end__gte=pe
        ).exists()
        if not exists:
            amount_cents = rng.choice([200000, 250000, 300000])  # colones * 100 (ajusta a tu moneda)
            Payment.objects.create(
                user_id=u.id,
                amount_cents=amount_cents,
                method=rng.choice(["efectivo", "transferencia", "sinpe"]),
                paid_at=now - timedelta(days=rng.randint(0, 5)),
                period_start=ps,
                period_end=pe,
                period_label=ps.strftime("%b-%Y"),
                notes="Pago demo",
            )


def unseed(apps, schema_editor):
    GymUser = apps.get_model("app", "GymUser")
    DailyTimeslot = apps.get_model("app", "DailyTimeslot")
    TimeslotSignup = apps.get_model("app", "TimeslotSignup")
    UserWeight = apps.get_model("app", "UserWeight")
    Payment = apps.get_model("app", "Payment")

    today = timezone.localdate()

    # Borra inscripciones DEMO del día de hoy
    TimeslotSignup.objects.filter(slot_date=today, user__full_name__startswith="[DEMO] ").delete()

    # Borra pesos y pagos de usuarios DEMO
    demo_users = GymUser.objects.filter(full_name__startswith="[DEMO] ")
    UserWeight.objects.filter(user__in=demo_users).delete()
    Payment.objects.filter(user__in=demo_users).delete()

    # Borra horarios diarios vacíos de hoy (opcional)
    DailyTimeslot.objects.filter(slot_date=today, signups__isnull=True).delete()

    # Borra usuarios DEMO
    demo_users.delete()


class Migration(migrations.Migration):

    # SI ya tienes una migración que siembra base_timeslots (p. ej. 0002_seed_base_timeslots),
    # déjala como dependencia. Si no, cámbiala por ("app", "0001_initial").
    dependencies = [
        ("app", "0001_initial"),
        # o: ("app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
