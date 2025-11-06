# app/migrations/00xx_link_gymuser_to_authuser.py
from django.db import migrations
from django.contrib.auth.hashers import make_password
from django.conf import settings

def forwards(apps, schema_editor):
    DjangoUser = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    GymUser = apps.get_model("app", "GymUser")

    for g in GymUser.objects.all():
        if g.user_id:
            continue

        username = str(g.id)
        u, created = DjangoUser.objects.get_or_create(
            username=username,
            defaults={
                "first_name": (g.full_name.split(" ", 1)[0] if g.full_name else ""),
                "last_name":  (g.full_name.split(" ", 1)[1] if (" " in g.full_name) else ""),
                "is_active": g.is_active,
                "password": make_password("gim12345"),  # ← en lugar de set_password
            },
        )
        if not created and not u.password:
            u.password = make_password("gim12345")
            u.save(update_fields=["password"])

        g.user_id = u.id
        g.save(update_fields=["user"])

def backwards(apps, schema_editor):
    GymUser = apps.get_model("app", "GymUser")
    for g in GymUser.objects.exclude(user_id=None):
        g.user_id = None
        g.save(update_fields=["user"])

class Migration(migrations.Migration):
    dependencies = [
        ("app", "0007_gymuser_user"),  # ajusta al número real previo
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),  # mejor que hardcodear "auth"
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
