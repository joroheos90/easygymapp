from django.db import migrations
from django.utils import timezone

def forwards(apps, schema_editor):
    Gym = apps.get_model("app", "Gym")
    GymUser = apps.get_model("app", "GymUser")
    BaseTimeslot = apps.get_model("app", "BaseTimeslot")
    DailyTimeslot = apps.get_model("app", "DailyTimeslot")
    TimeslotSignup = apps.get_model("app", "TimeslotSignup")
    Payment = apps.get_model("app", "Payment")
    UserWeight = apps.get_model("app", "UserWeight")

    default_gym, _ = Gym.objects.get_or_create(
        name="Default Gym",
        defaults={"address": "", "is_active": True, "created_at": timezone.now()},
    )

    for gu in GymUser.objects.filter(gym__isnull=True):
        gu.gym_id = default_gym.id
        gu.save(update_fields=["gym"])

    for bt in BaseTimeslot.objects.filter(gym__isnull=True):
        bt.gym_id = default_gym.id
        bt.save(update_fields=["gym"])

    for dt in DailyTimeslot.objects.filter(gym__isnull=True):
        if dt.base_id and getattr(dt.base, "gym_id", None):
            dt.gym_id = dt.base.gym_id
        else:
            dt.gym_id = default_gym.id
        dt.save(update_fields=["gym"])

    for sg in TimeslotSignup.objects.filter(gym__isnull=True):
        if sg.daily_slot_id and getattr(sg.daily_slot, "gym_id", None):
            sg.gym_id = sg.daily_slot.gym_id
        elif sg.user_id and getattr(sg.user, "gym_id", None):
            sg.gym_id = sg.user.gym_id
        else:
            sg.gym_id = default_gym.id
        sg.save(update_fields=["gym"])

    for p in Payment.objects.filter(gym__isnull=True):
        if p.user_id and getattr(p.user, "gym_id", None):
            p.gym_id = p.user.gym_id
        else:
            p.gym_id = default_gym.id
        p.save(update_fields=["gym"])

    for w in UserWeight.objects.filter(gym__isnull=True):
        if w.user_id and getattr(w.user, "gym_id", None):
            w.gym_id = w.user.gym_id
        else:
            w.gym_id = default_gym.id
        w.save(update_fields=["gym"])

def backwards(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("app", "0011_gym_remove_dailytimeslot_uniq_daily_date_title_and_more"),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
