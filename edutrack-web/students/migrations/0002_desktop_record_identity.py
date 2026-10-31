from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_campus_desktop_bundle"),
        ("students", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DesktopRecordIdentity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "record_type",
                    models.CharField(
                        choices=[
                            ("student", "Estudiante"),
                            ("enrollment", "Matrícula"),
                            ("course", "Curso"),
                            ("promoter", "Promotor"),
                        ],
                        max_length=16,
                    ),
                ),
                ("local_id", models.CharField(max_length=36)),
                ("server_id", models.PositiveBigIntegerField()),
                (
                    "campus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="desktop_record_identities",
                        to="core.campus",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="desktoprecordidentity",
            constraint=models.UniqueConstraint(
                fields=("campus", "record_type", "local_id"),
                name="desktop_identity_local",
            ),
        ),
        migrations.AddConstraint(
            model_name="desktoprecordidentity",
            constraint=models.UniqueConstraint(
                fields=("campus", "record_type", "server_id"),
                name="desktop_identity_server",
            ),
        ),
    ]
