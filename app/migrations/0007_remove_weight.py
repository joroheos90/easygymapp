from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0006_alter_activitylog_event_type_measurementdefinition_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="UserWeight",
        ),
    ]
