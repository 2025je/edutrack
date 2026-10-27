from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_role_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="campus",
            name="desktop_bundle_id",
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                unique=True,
            ),
        ),
    ]
