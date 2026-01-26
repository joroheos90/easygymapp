from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Tuple
from dateutil.relativedelta import relativedelta
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
)


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
