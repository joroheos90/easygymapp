# app/migrations/00xx_create_initial_superuser.py
import os
from django.db import migrations
from django.contrib.auth.hashers import make_password
from django.conf import settings

def forwards(apps, schema_editor):
    # Lee credenciales desde variables de entorno (recomendado en Render)
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
    email    = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "change-me-now")

    # Obtén el modelo de usuario “histórico” (compatible con custom user)
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    # Crea o actualiza de forma idempotente
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "password": make_password(password),
        },
    )

    if not created:
        # Asegura flags de superusuario/staff
        changed = False
        if not user.is_staff:
            user.is_staff = True; changed = True
        if not user.is_superuser:
            user.is_superuser = True; changed = True
        # Si vino PASSWORD en env, actualiza el password
        if os.environ.get("DJANGO_SUPERUSER_PASSWORD"):
            user.password = make_password(password); changed = True
        # Si vino EMAIL en env, actualiza email
        if os.environ.get("DJANGO_SUPERUSER_EMAIL"):
            user.email = email; changed = True
        if changed:
            user.save(update_fields=["is_staff","is_superuser","is_active","password","email"])

def backwards(apps, schema_editor):
    # opcional: no borramos al superuser para no perder acceso
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("app", "0009_alter_gymuser_user"),  # <-- ajusta al número real
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
