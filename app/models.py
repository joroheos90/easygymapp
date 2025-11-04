from django.db import models
from django.utils import timezone


class GymUser(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    id = models.BigAutoField(primary_key=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    join_date = models.DateField()               # ancla para calcular periodos
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=32, null=True, blank=True)
    height_cm = models.CharField(max_length=5, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["join_date"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self):
        return self.full_name


class Payment(models.Model):
    class Method(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"
        SINPE = "sinpe", "SINPE"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(GymUser, on_delete=models.CASCADE, related_name="payments")
    amount = models.PositiveIntegerField()
    method = models.CharField(max_length=20, choices=Method.choices)
    paid_at = models.DateTimeField(default=timezone.now)

    period_start = models.DateField()
    period_end = models.DateField()                # recomendado: fin exclusivo
    period_label = models.CharField(max_length=40, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        constraints = [
            models.CheckConstraint(check=models.Q(period_end__gt=models.F("period_start")),
                                   name="payments_period_end_gt_start"),
        ]
        indexes = [
            models.Index(fields=["user", "period_start", "period_end"], name="idx_pay_user_period"),
            models.Index(fields=["paid_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.period_label or ''}".strip()


class BaseTimeslot(models.Model):
    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=80)             # "6 am a 7 am"
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "base_timeslots"

    def __str__(self):
        return self.title


class DailyTimeslot(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.BigAutoField(primary_key=True)
    slot_date = models.DateField()
    base = models.ForeignKey(
        BaseTimeslot, null=True, blank=True, on_delete=models.SET_NULL, related_name="instances"
    )
    title = models.CharField(max_length=80)             # copia del base o personalizado
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "daily_timeslots"
        constraints = [
            models.UniqueConstraint(fields=["slot_date", "title"], name="uniq_daily_date_title"),
        ]
        indexes = [
            models.Index(fields=["slot_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.slot_date} {self.title}"


class TimeslotSignup(models.Model):
    id = models.BigAutoField(primary_key=True)
    daily_slot = models.ForeignKey(DailyTimeslot, on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(GymUser, on_delete=models.CASCADE, related_name="signups")
    signed_at = models.DateTimeField(default=timezone.now)
    slot_date = models.DateField()  # denormalizado para reglas rápidas (1 por día, etc.)

    class Meta:
        db_table = "timeslot_signups"
        constraints = [
            models.UniqueConstraint(fields=["daily_slot", "user"], name="uniq_signup_slot_user"),
            # Si NO quieres limitar a 1 horario por día, elimina esta línea:
            models.UniqueConstraint(fields=["user", "slot_date"], name="uniq_signup_user_day"),
        ]
        indexes = [
            models.Index(fields=["user", "slot_date"], name="idx_signup_user_date"),
        ]


class UserWeight(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(GymUser, on_delete=models.CASCADE, related_name="weights")
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "user_weights"
        indexes = [
            models.Index(fields=["user", "recorded_at"]),
        ]
