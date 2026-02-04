from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Tuple
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from django.contrib.auth import get_user_model
from uuid import uuid4


from django.db import transaction, IntegrityError
from django.db.models import Count, Q, F
from django.utils import timezone

from .models import (
    GymUser,
    Payment,
    BaseTimeslot,
    DailyTimeslot,
    TimeslotSignup,
    MeasurementValue,
    MeasurementDefinition,
)
from .activity.helpers import log_activity
from .activity.event_types import ActivityEventType
from .helpers import slot_start_dt, current_period_for



# ---------- Domain errors ----------
class ServiceError(Exception):
    """Base error for service layer."""


class NotFound(ServiceError):
    pass


class ValidationError(ServiceError):
    pass


# ---------- Helpers ----------
def to_cents(amount: float | int) -> int:
    """Convert a decimal amount to cents (int)."""
    return int(round(float(amount) * 100))


def current_period_for(user: GymUser, ref: Optional[date] = None) -> Tuple[date, date]:
    """
    Monthly period anchored to user's join_date day.
    End is exclusive.
    """
    today = ref or date.today()
    base_day = user.join_date.day

    # If today's day is before base_day, current period started last month at base_day.
    if today.day < base_day:
        start = (today.replace(day=1) - relativedelta(months=1)).replace(day=base_day)
    else:
        start = today.replace(day=base_day)
    end = start + relativedelta(months=1)
    return start, end


# ---------- Read models (DTOs) ----------
@dataclass(frozen=True)
class RosterItem:
    user_id: int
    full_name: str
    signed_at: timezone.datetime


@dataclass(frozen=True)
class SlotStatus:
    id: int
    slot_date: date
    title: str
    capacity: int
    status: str
    enrolled: int
    available: int


# ---------- Service ----------
class GymService:
    @transaction.atomic
    def crear_gymuser_y_user(gym, full_name: str, is_active: bool = True, password: str = "gim12345", role="member"):
        UserModel = get_user_model()

        tmp_username = f"tmp-{uuid4().hex}"
        u = UserModel.objects.create_user(username=tmp_username, password=password)
        parts = (full_name or "").strip().split(" ", 1)
        u.first_name = parts[0] if parts else ""
        u.last_name  = parts[1] if len(parts) > 1 else ""
        u.is_active  = is_active
        u.save(update_fields=["first_name", "last_name", "is_active"])

        g = GymUser.objects.create(
            gym=gym,
            user=u,
            full_name=full_name or "Sin nombre",
            role=role,
            join_date=timezone.localdate(),
            is_active=is_active,
        )

        final_username = str(g.id)
        if u.username != final_username:
            u.username = final_username
            u.save(update_fields=["username"])

        return g, u


    @staticmethod
    def update_user(user_id: int, **fields) -> GymUser:
        user = GymService.get_user(user_id)
        allowed = {"full_name", "role", "join_date", "birth_date", "is_active", "phone"}
        updates = []
        for k, v in fields.items():
            if k in allowed:
                setattr(user, k, v)
                updates.append(k)
        if updates:
            user.save(update_fields=updates + ["updated_at"])
        return user

    @staticmethod
    def find_user_by_phone(phone: str):
        return GymUser.objects.filter(phone__iexact=(phone or "").strip()).first()

    @staticmethod
    def get_user(user_id: int) -> GymUser:
        try:
            return GymUser.objects.get(id=user_id)
        except GymUser.DoesNotExist:
            raise NotFound("User not found.")


    @staticmethod
    def list_users(*, active_only: bool = True):
        qs = GymUser.objects.all().order_by("full_name")
        if active_only:
            qs = qs.filter(is_active=True)
        return qs

    # ===== PAYMENTS =====
    @staticmethod
    def add_payment(*, user_id: int, amount: float | int, method: str,
                    period_start: date, period_end: date,
                    period_label: Optional[str] = None, notes: Optional[str] = None) -> Payment:
        if period_end <= period_start:
            raise ValidationError("period_end must be greater than period_start.")
        user = GymService.get_user(user_id)
        return Payment.objects.create(
            user=user,
            amount_cents=to_cents(amount),
            method=method,
            paid_at=timezone.now(),
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            notes=notes,
        )

    @staticmethod
    def add_payment_for_current_period(*, user_id: int, amount: float | int, method: str,
                                       label_fmt: str = "%b-%Y") -> Payment:
        user = GymService.get_user(user_id)
        ps, pe = current_period_for(user)
        return GymService.add_payment(
            user_id=user.id,
            amount=amount,
            method=method,
            period_start=ps,
            period_end=pe,
            period_label=f"{ps.strftime(label_fmt)}",
        )

    @staticmethod
    def user_has_paid_current_period(user_id: int) -> bool:
        user = GymService.get_user(user_id)
        ps, pe = current_period_for(user)
        return Payment.objects.filter(
            user=user, period_start__lte=ps, period_end__gte=pe
        ).exists()

    @staticmethod
    def list_debtors(*, ref: Optional[date] = None):
        """
        Users without a payment covering their current period (anchored to their join_date).
        For performance, compute period per user in Python for small gyms; for big data, denormalize periods.
        """
        today = ref or date.today()
        result = []
        for u in GymService.list_users(active_only=True):
            ps, pe = current_period_for(u, ref=today)
            paid = Payment.objects.filter(user=u, period_start__lte=ps, period_end__gte=pe).exists()
            if not paid:
                result.append(u)
        return result

    @staticmethod
    def list_user_payments(user_id: int):
        user = GymService.get_user(user_id)
        return user.payments.order_by("-paid_at")


    # ===== BASE TIMESLOTS =====
    @staticmethod
    def create_base_timeslot(*, title: str, capacity: int, is_active: bool = True) -> BaseTimeslot:
        return BaseTimeslot.objects.create(title=title, capacity=capacity, is_active=is_active)

    @staticmethod
    def update_base_timeslot(slot_id: int, **fields) -> BaseTimeslot:
        try:
            base = BaseTimeslot.objects.get(id=slot_id)
        except BaseTimeslot.DoesNotExist:
            raise NotFound("Base timeslot not found.")
        allowed = {"title", "capacity", "is_active"}
        for k, v in fields.items():
            if k in allowed:
                setattr(base, k, v)
        base.save(update_fields=list(allowed & set(fields.keys())) + ["updated_at"])
        return base

    @staticmethod
    def list_base_timeslots(active_only: bool = True):
        qs = BaseTimeslot.objects.all().order_by("title")
        if active_only:
            qs = qs.filter(is_active=True)
        return qs

    # ===== DAILY TIMESLOTS =====
    @staticmethod
    def ensure_daily_from_base_for_range(*, start: date, end: date) -> int:
        """
        Create daily instances copying active bases for every date in [start, end] inclusive
        if not already present. Returns number of created daily slots.
        """
        if end < start:
            raise ValidationError("end must be >= start.")
        bases = list(BaseTimeslot.objects.filter(is_active=True).order_by("id"))
        created = 0
        with transaction.atomic():
            d = start
            while d <= end:
                for b in bases:
                    try:
                        DailyTimeslot.objects.get(slot_date=d, title=b.title)
                    except DailyTimeslot.DoesNotExist:
                        DailyTimeslot.objects.create(
                            slot_date=d,
                            base=b,
                            title=b.title,
                            capacity=b.capacity,
                            status=DailyTimeslot.Status.OPEN,
                        )
                        created += 1
                d += timedelta(days=1)
        return created

    @staticmethod
    def update_daily_timeslot(slot_id: int, **fields) -> DailyTimeslot:
        try:
            ds = DailyTimeslot.objects.get(id=slot_id)
        except DailyTimeslot.DoesNotExist:
            raise NotFound("Daily timeslot not found.")
        allowed = {"title", "capacity", "status"}
        for k, v in fields.items():
            if k in allowed:
                setattr(ds, k, v)
        ds.save(update_fields=list(allowed & set(fields.keys())))
        return ds

    @staticmethod
    def get_daily_slot(slot_id: int) -> DailyTimeslot:
        try:
            return DailyTimeslot.objects.get(id=slot_id)
        except DailyTimeslot.DoesNotExist:
            raise NotFound("Daily timeslot not found.")

    @staticmethod
    def list_daily_by_date(day: date):
        return DailyTimeslot.objects.filter(slot_date=day).annotate(
            enrolled=Count("signups")
        ).order_by("title")

    @staticmethod
    def slot_status(slot_id: int) -> SlotStatus:
        d = (
            DailyTimeslot.objects.filter(id=slot_id)
            .annotate(enrolled=Count("signups"))
            .values("id", "slot_date", "title", "capacity", "status", "enrolled")
            .first()
        )
        if not d:
            raise NotFound("Daily timeslot not found.")
        return SlotStatus(
            id=d["id"],
            slot_date=d["slot_date"],
            title=d["title"],
            capacity=d["capacity"],
            status=d["status"],
            enrolled=d["enrolled"],
            available=d["capacity"] - d["enrolled"],
        )

    @staticmethod
    @transaction.atomic
    def close_slot(slot_id: int) -> DailyTimeslot:
        ds = GymService.get_daily_slot(slot_id)
        ds.status = DailyTimeslot.Status.CLOSED
        ds.save(update_fields=["status"])
        return ds

    @staticmethod
    @transaction.atomic
    def cancel_slot(slot_id: int) -> DailyTimeslot:
        ds = GymService.get_daily_slot(slot_id)
        ds.status = DailyTimeslot.Status.CANCELLED
        ds.save(update_fields=["status"])
        return ds

    # ===== SIGNUPS =====
    @staticmethod
    @transaction.atomic
    def signup_user_to_slot(*, user_id: int, daily_slot_id: int) -> TimeslotSignup:
        user = GymService.get_user(user_id)
        try:
            ds = DailyTimeslot.objects.select_for_update().get(id=daily_slot_id)
        except DailyTimeslot.DoesNotExist:
            raise NotFound("Daily timeslot not found.")

        if ds.status != DailyTimeslot.Status.OPEN:
            raise ValidationError("Timeslot is not open.")

        # Capacity check
        enrolled = TimeslotSignup.objects.filter(daily_slot=ds).count()
        if enrolled >= ds.capacity:
            raise ValidationError("Timeslot is full.")

        # Enforce one-per-day rule if the UniqueConstraint exists
        try:
            signup = TimeslotSignup.objects.create(
                daily_slot=ds,
                user=user,
                signed_at=timezone.now(),
                slot_date=ds.slot_date,
            )
        except IntegrityError as e:
            raise ValidationError("User already signed for this day or slot.") from e

        return signup

    @staticmethod
    @transaction.atomic
    def unsign_user_from_slot(*, user_id: int, daily_slot_id: int) -> None:
        deleted, _ = TimeslotSignup.objects.filter(
            daily_slot_id=daily_slot_id, user_id=user_id
        ).delete()
        if deleted == 0:
            raise NotFound("Signup not found.")

    @staticmethod
    def roster(daily_slot_id: int) -> Iterable[RosterItem]:
        qs = (
            TimeslotSignup.objects.filter(daily_slot_id=daily_slot_id)
            .select_related("user")
            .order_by("signed_at")
        )
        for s in qs:
            yield RosterItem(
                user_id=s.user_id, full_name=s.user.full_name, signed_at=s.signed_at
            )

    # ===== DASHBOARD HELPERS =====
    @staticmethod
    def day_overview(day: date) -> Iterable[SlotStatus]:
        qs = (
            DailyTimeslot.objects.filter(slot_date=day)
            .annotate(enrolled=Count("signups"))
            .order_by("title")
            .values("id", "slot_date", "title", "capacity", "status", "enrolled")
        )
        for d in qs:
            yield SlotStatus(
                id=d["id"],
                slot_date=d["slot_date"],
                title=d["title"],
                capacity=d["capacity"],
                status=d["status"],
                enrolled=d["enrolled"],
                available=d["capacity"] - d["enrolled"],
            )


class BodyMetricsService:

    @staticmethod
    def get_metrics(user_id: int, month: int, year: int) -> dict:
        user = GymUser.objects.only(
            "id", "birth_date", "sex", "height_cm"
        ).get(id=user_id)

        has_values = MeasurementValue.objects.filter(record__user_id=user_id).exists()

        if not has_values:
            return {}

        if not user.birth_date or not user.height_cm:
            return {}
        
        age = BodyMetricsService._calculate_age(user.birth_date)

        return {
            "weight": BodyMetricsService._weight_metric(user, age, month, year),
            "waist": BodyMetricsService._waist_metric(user, month, year),
            "muscle": BodyMetricsService._muscle_metric(user, month, year),
            "body_fat": BodyMetricsService._body_fat_metric(user, age, month, year),
            "bmi": BodyMetricsService._bmi_metric(user, month, year),
        }


    # -------------------------
    # Helpers
    # -------------------------

    @staticmethod
    def _calculate_age(birth_date):
        today = date.today()
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )

    @staticmethod
    def _get_trend_values(user_id, code, month, year):
        last_day = monthrange(year, month)[1]
        end_of_base_month = date(
            year,
            month,
            last_day
        )
        qs = (
                MeasurementValue.objects
                .filter(
                    record__user_id=user_id,
                    definition_code=code,
                    record__record_date__lte=end_of_base_month,
                )
                .select_related("record")
                .order_by("-record__record_date")[:12]
            )

        values = [
            {
                "value": float(v.value),
                "date": v.record.record_date,
                "label": v.record.record_date.strftime("%b"),
                "definition_name": v.definition_name if v.definition_name else v.definition_code,
            }
            for v in reversed(qs)
        ]

        def _normalize(values, min_height=10, max_height=100):
            if not values:
                return values

            nums = [v["value"] for v in values]
            vmin, vmax = min(nums), max(nums)

            for v in values:
                if vmax == vmin:
                    v["height"] = 60  # plano si no hay variación
                else:
                    v["height"] = round(
                        min_height + (v["value"] - vmin) * (max_height - min_height) / (vmax - vmin)
                    )

            return values


        return _normalize(values)


    @staticmethod
    def _build_trend(values):
        if len(values) < 2:
            return {"delta": None, "direction": None, "values": values}

        delta = round(values[-1]["value"] - values[0]["value"], 1)

        return {
            "delta": delta,
            "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
            "values": values,
        }

    # -------------------------
    # Peso
    # -------------------------

    @staticmethod
    def _weight_metric(user, age, month, year):
        values = BodyMetricsService._get_trend_values(
            user.id, MeasurementDefinition.MeasurementCode.WEIGHT, month, year
        )

        current = values[-1] if values else {}
        current_value = current.get("value", 0)

        min_w, max_w, ideal = BodyMetricsService._weight_range(user)

        status = BodyMetricsService._status(current_value, min_w, max_w)

        return {
            "name": current.get("definition_name", ""),
            "unit": "kg",
            "current": current_value,
            "range": {"min": min_w, "max": max_w, "ideal": ideal},
            "status": status,
            "trend": BodyMetricsService._build_trend(values),
        }

    @staticmethod
    def _weight_range(user):
        if not user.height_cm:
            return None, None, None

        bmi_min, bmi_max = 18.5, 24.9
        h = user.height_cm / 100

        weight_min = round(bmi_min * h * h, 1)
        weight_max = round(bmi_max * h * h, 1)
        weight_ideal = round((weight_min + weight_max) / 2, 1)

        return weight_min, weight_max, weight_ideal


    # -------------------------
    # Cintura
    # -------------------------

    @staticmethod
    def _waist_metric(user, month, year):
        values = BodyMetricsService._get_trend_values(
            user.id, MeasurementDefinition.MeasurementCode.WAIST, month, year
        )

        current = values[-1] if values else {}
        current_value = current.get("value", 0)

        min_w, max_w = BodyMetricsService._waist_range(user.sex)

        status = BodyMetricsService._status(current_value, min_w, max_w)

        return {
            "name": current.get("definition_name", ""),
            "unit": "cm",
            "current": current_value,
            "range": {"min": min_w, "max": max_w},
            "status": status,
            "trend": BodyMetricsService._build_trend(values),
        }

    @staticmethod
    def _waist_range(sex):
        if sex == "male":
            return 70, 94
        return 60, 80 
    
    @staticmethod
    def _muscle_metric(user, month, year):
        values = BodyMetricsService._get_trend_values(
            user.id, MeasurementDefinition.MeasurementCode.MUSCLE_MASS, month, year
        )

        current = values[-1] if values else {}
        current_value = current.get("value", 0)
        min_v, max_v = BodyMetricsService._muscle_range(user.sex)

        return {
            "name": current.get("definition_name", ""),
            "unit": "%",
            "current": current_value,
            "range": {"min": min_v, "max": max_v},
            "status": BodyMetricsService._status(current_value, min_v, max_v),
            "trend": BodyMetricsService._build_trend(values),
        }

    @staticmethod
    def _muscle_range(sex):
        if sex == "male":
            return 33, 39
        return 24, 30
    

    @staticmethod
    def _body_fat_metric(user, age, month, year):
        values = BodyMetricsService._get_trend_values(
            user.id, MeasurementDefinition.MeasurementCode.BODY_FAT_PERCENT, month, year
        )

        current = values[-1] if values else {}
        current_value = current.get("value", 0)
        min_v, max_v = BodyMetricsService._body_fat_range(user.sex, age)

        return {
            "name": current.get("definition_name", ""),
            "unit": "%",
            "current": current_value,
            "range": {"min": min_v, "max": max_v},
            "status": BodyMetricsService._status(current_value, min_v, max_v),
            "trend": BodyMetricsService._build_trend(values),
        }


    @staticmethod
    def _body_fat_range(sex, age):
        if sex == "male":
            if age < 40:
                return 8, 19
            if age < 60:
                return 11, 22
            return 13, 25

        # female
        if age < 40:
            return 21, 32
        if age < 60:
            return 23, 35
        return 24, 36

    @staticmethod
    def _bmi_metric(user, month, year):
        # usamos el último peso del mes
        values = BodyMetricsService._get_trend_values(
            user.id, MeasurementDefinition.MeasurementCode.WEIGHT, month, year
        )

        if not values or not user.height_cm:
            return {
                "name": "bmi",
                "unit": "kg/m2",
                "current": None,
                "range": {"min": 18.5, "max": 24.9},
                "status": None,
                "trend": None,
            }

        h = user.height_cm / 100
        bmi_values = []

        for v in values:
            bmi = round(v["value"] / (h * h), 1)
            bmi_values.append({
                "date": v["date"],
                "value": bmi,
            })

        current = bmi_values[-1]["value"]
        min_v, max_v = 18.5, 24.9

        return {
            "name": "bmi",
            "unit": "kg/m2",
            "current": current,
            "range": {"min": min_v, "max": max_v},
            "status": BodyMetricsService._status(current, min_v, max_v),
            "trend": BodyMetricsService._build_trend(bmi_values),
        }


    # -------------------------
    # Status común
    # -------------------------

    @staticmethod
    def _status(value, min_v, max_v):
        if value is None or min_v is None:
            return None
        if value < min_v:
            return "low"
        if max_v and value > max_v:
            return "high"
        return "ok"


class TimeslotPolicy:
    def __init__(self, *, is_admin, now):
        self.is_admin = is_admin
        self.now = now

    @property
    def enforce_time_rules(self):
        return not self.is_admin

    def can_use_slot(self, slot):
        if slot.status != DailyTimeslot.Status.OPEN:
            return False, "Este horario no está disponible."

        start = slot_start_dt(slot)
        if start is None:
            return False, "Este horario no tiene hora configurada."

        if self.enforce_time_rules and start <= self.now:
            return False, "Este horario ya inició o ya pasó."

        return True, None

    def can_join(self, slot):
        if not self.enforce_time_rules:
            return True, None

        if self.now >= slot_start_dt(slot) - timedelta(hours=1):
            return False, "No puedes inscribirte si falta menos de 1 hora."

        return True, None

    def can_cancel(self, slot):
        if not self.enforce_time_rules:
            return True, None

        if self.now >= slot_start_dt(slot) - timedelta(minutes=30):
            return False, "No puedes cancelar si falta 1 hora o menos."

        return True, None

    def can_switch_from(self, slot):
        if not self.enforce_time_rules:
            return True, None

        start = slot_start_dt(slot)
        if start is None:
            return False, (
                "Tu horario actual no tiene hora configurada; "
                "no es posible cambiar."
            )

        if self.now >= start - timedelta(hours=1):
            return False, (
                "No puedes cambiar de horario si falta 1 hora o menos "
                "para tu horario actual."
            )

        return True, None


class TimeslotService:
    def __init__(self, *, request, user, slot):
        self.request = request
        self.user = user
        self.slot = slot
        self.gym = request.gym
        self.now = timezone.now()

        self.policy = TimeslotPolicy(
            is_admin=request.is_admin,
            now=self.now,
        )

    def execute(self):
        # --------------------------------------------------------------
        # VALIDACIÓN BASE DEL SLOT
        # --------------------------------------------------------------
        allowed, error = self.policy.can_use_slot(self.slot)
        if not allowed:
            return None, error

        day = self.slot.slot_date

        existing = (
            TimeslotSignup.objects
            .select_for_update()
            .select_related("daily_slot")
            .filter(
                gym=self.gym,
                user=self.user,
                slot_date=day,
            )
            .first()
        )

        # --------------------------------------------------------------
        # CANCELACIÓN
        # --------------------------------------------------------------
        if existing and existing.daily_slot_id == self.slot.id:
            allowed, error = self.policy.can_cancel(self.slot)
            if not allowed:
                return None, error

            existing.delete()
            self._log_leave()
            return "Se canceló tu registro con éxito.", None

        # --------------------------------------------------------------
        # INSCRIPCIÓN / CAMBIO
        # --------------------------------------------------------------
        allowed, error = self.policy.can_join(self.slot)
        if not allowed:
            return None, error

        if existing:
            allowed, error = self.policy.can_switch_from(
                existing.daily_slot
            )
            if not allowed:
                return None, error

        # --------------------------------------------------------------
        # PAGO
        # --------------------------------------------------------------
        if not self._has_active_payment():
            return None, "Debes tener tu pago al día para inscribirte."

        # --------------------------------------------------------------
        # CUPO
        # --------------------------------------------------------------
        if not self._has_capacity():
            return None, "Este horario ya está lleno."

        # --------------------------------------------------------------
        # EJECUCIÓN
        # --------------------------------------------------------------
        if existing:
            existing.delete()

        TimeslotSignup.objects.create(
            gym=self.gym,
            daily_slot=self.slot,
            user=self.user,
            slot_date=day,
            signed_at=self.now,
        )

        self._log_join()
        return "Registro completado con éxito.", None

    # --------------------------------------------------------------
    # HELPERS INTERNOS
    # --------------------------------------------------------------
    def _has_active_payment(self):
        ps, pe = current_period_for(self.user, ref=timezone.localdate())
        return Payment.objects.filter(
            gym=self.gym,
            user=self.user,
            period_start__lte=ps,
            period_end__gte=pe,
        ).exists()

    def _has_capacity(self):
        capacity = self.slot.capacity or 0
        if capacity <= 0:
            return False

        enrolled = TimeslotSignup.objects.filter(
            daily_slot=self.slot
        ).count()

        return enrolled < capacity

    def _log_join(self):
        log_activity(
            gym=self.gym,
            actor=self.request.user,
            event_type=ActivityEventType.GROUP_JOIN,
            metadata={
                "group_title": self.slot.title,
                "group_date": self.slot.slot_date.strftime("%d/%m/%Y"),
            },
        )

    def _log_leave(self):
        log_activity(
            gym=self.gym,
            actor=self.request.user,
            event_type=ActivityEventType.GROUP_LEAVE,
            metadata={
                "group_title": self.slot.title,
                "group_date": self.slot.slot_date.strftime("%d/%m/%Y"),
            },
        )
