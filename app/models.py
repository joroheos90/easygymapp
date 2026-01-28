from django.db import models
from django.utils import timezone
from django.conf import settings
from .activity.event_types import ActivityEventType

class Gym(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gyms"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name


class GymUser(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gym_profile",
        null=False, blank=False,
    )
    gym  = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="members",
                             null=False, blank=False)

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        STAFF = "staff", "Staff"

    id = models.BigAutoField(primary_key=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    join_date = models.DateField()
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=32, null=True, blank=True)
    height_cm = models.CharField(max_length=5, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["gym", "is_active"]),
            models.Index(fields=["gym", "join_date"]),
            models.Index(fields=["gym", "phone"]),
        ]

    def __str__(self):
        return f"[{self.gym_id}] {self.full_name} (u:{self.user_id})"


class Payment(models.Model):
    class Method(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        SINPE = "sinpe", "SINPE"

    id = models.BigAutoField(primary_key=True)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="payments",
                            null=False, blank=False)  # <-- Fase 1: NULLABLE
    user = models.ForeignKey(GymUser, on_delete=models.CASCADE, related_name="payments")
    amount = models.PositiveIntegerField()
    method = models.CharField(max_length=20, choices=Method.choices)
    paid_at = models.DateTimeField(default=timezone.now)

    period_start = models.DateField()
    period_end = models.DateField()
    period_label = models.CharField(max_length=40, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        constraints = [
            models.CheckConstraint(
                check=models.Q(period_end__gt=models.F("period_start")),
                name="payments_period_end_gt_start",
            ),
        ]
        indexes = [
            models.Index(fields=["gym", "user", "period_start", "period_end"], name="idx_pay_gym_user_period"),
            models.Index(fields=["gym", "paid_at"]),
        ]

    def __str__(self):
        return f"[{self.gym_id}] {self.user_id} {self.period_label or ''} {self.method}".strip()


class BaseTimeslot(models.Model):
    id = models.BigAutoField(primary_key=True)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="base_slots",
                            null=False, blank=False)  # <-- Fase 1: NULLABLE
    title = models.CharField(max_length=80)
    capacity = models.PositiveIntegerField()
    day_order = models.PositiveIntegerField(blank=False, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    start_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = "base_timeslots"
        constraints = [
            models.UniqueConstraint(fields=["gym", "title"], name="uniq_base_title_per_gym"),
        ]
        indexes = [
            models.Index(fields=["gym", "is_active"]),
            models.Index(fields=["day_order"]),
        ]
        ordering = ["day_order"] 

    def __str__(self):
        return f"[{self.gym_id}] {self.title}"


class DailyTimeslot(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.BigAutoField(primary_key=True)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="daily_slots",
                            null=False, blank=False)  # <-- Fase 1: NULLABLE
    slot_date = models.DateField()
    base = models.ForeignKey(
        BaseTimeslot, null=True, blank=True, on_delete=models.SET_NULL, related_name="instances"
    )
    title = models.CharField(max_length=80)
    capacity = models.PositiveIntegerField()
    day_order = models.PositiveIntegerField(blank=False, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(default=timezone.now)
    start_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = "daily_timeslots"
        constraints = [
            models.UniqueConstraint(fields=["gym", "slot_date", "title"], name="uniq_daily_date_title_per_gym"),
        ]
        ordering = ["day_order"] 
        indexes = [
            models.Index(fields=["gym", "slot_date"]),
            models.Index(fields=["gym", "status"]),
            models.Index(fields=["day_order"]),
        ]

    def __str__(self):
        return f"[{self.gym_id}] {self.slot_date} {self.title}"


class TimeslotSignup(models.Model):
    id = models.BigAutoField(primary_key=True)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="signups",
                            null=False, blank=False)  # <-- Fase 1: NULLABLE
    daily_slot = models.ForeignKey(DailyTimeslot, on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(GymUser, on_delete=models.CASCADE, related_name="signups")
    signed_at = models.DateTimeField(default=timezone.now)
    slot_date = models.DateField()

    class Meta:
        db_table = "timeslot_signups"
        constraints = [
            models.UniqueConstraint(fields=["daily_slot", "user"], name="uniq_signup_slot_user"),
            models.UniqueConstraint(fields=["gym", "user", "slot_date"], name="uniq_signup_user_day_per_gym"),
        ]
        indexes = [
            models.Index(fields=["gym", "user", "slot_date"], name="idx_signup_gym_user_date"),
        ]


class ActivityLog(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="activity_logs",
                            null=True, blank=True)

    actor_id = models.PositiveIntegerField(null=True, blank=True)
    actor_name = models.CharField(max_length=255)

    event_type = models.CharField(
        max_length=50,
        choices=ActivityEventType.choices
    )

    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MeasurementDefinition(models.Model):
    class UnitType(models.TextChoices):
        CM = "cm", "Centímetros"
        KG = "kg", "Kilogramos"
        PERCENT = "%", "Porcentaje"
        TEXT = "text", "Texto"
        NUMBER = "#", "Número"

    id = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=80)

    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices
    )

    priority = models.PositiveSmallIntegerField(
        default=100,
    )

    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "measurement_definitions"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["unit_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.unit_type})"


class MeasurementRecord(models.Model):
    id = models.BigAutoField(primary_key=True)

    gym = models.ForeignKey(
        Gym,
        on_delete=models.CASCADE,
        related_name="measurement_records"
    )
    user = models.ForeignKey(
        GymUser,
        on_delete=models.CASCADE,
        related_name="measurement_records"
    )

    record_date = models.DateField()
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "measurement_records"
        constraints = [
            models.UniqueConstraint(
                fields=["gym", "user", "record_date"],
                name="uniq_measurement_record_user_date"
            ),
        ]
        indexes = [
            models.Index(fields=["gym", "user", "record_date"]),
        ]

    def __str__(self):
        return f"[{self.gym_id}] {self.user_id} {self.record_date}"


class MeasurementValue(models.Model):
    id = models.BigAutoField(primary_key=True)

    record = models.ForeignKey(
        MeasurementRecord,
        on_delete=models.CASCADE,
        related_name="values"
    )

    # Snapshot inmutable
    definition_name = models.CharField(max_length=80)
    unit_type = models.CharField(max_length=20)
    priority = models.PositiveSmallIntegerField(
        null=True,
        blank=True
    )

    value = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "measurement_values"

    def __str__(self):
        return f"{self.definition_name}: {self.value}"
