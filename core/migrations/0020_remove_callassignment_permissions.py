from django.db import migrations


def remove_stale_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="calls", model="callassignment").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_user_onboarding"),
        ("calls", "0008_call_lists"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(remove_stale_permissions, migrations.RunPython.noop),
    ]
