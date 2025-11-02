from django.db import migrations

def forward(apps, schema_editor):
    GymUser = apps.get_model("app", "GymUser")
    for i, u in enumerate(GymUser.objects.filter(phone__isnull=True)):
        u.phone = f"8888-77{i:02d}"  # string simple
        u.save(update_fields=["phone"])

def backward(apps, schema_editor):
    GymUser = apps.get_model("app", "GymUser")
    GymUser.objects.update(phone=None)

class Migration(migrations.Migration):
    dependencies = [("app", "0003_gymuser_phone_gymuser_users_phone_af6883_idx")]  # ajusta al nombre real
    operations = [migrations.RunPython(forward, backward)]
