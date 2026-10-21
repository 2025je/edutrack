import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assignments_to_lists(apps, schema_editor):
    """Cada usuario con asignaciones pasa a una sublista propia con sus mismas matrículas."""
    CallAssignment = apps.get_model("calls", "CallAssignment")
    CallList = apps.get_model("calls", "CallList")
    CallListMember = apps.get_model("calls", "CallListMember")
    grouped = {}
    for item in CallAssignment.objects.select_related("user", "enrollment").order_by("pk"):
        key = (item.user_id, item.enrollment.campus_id)
        grouped.setdefault(key, []).append(item)
    joined = set()
    for (user_id, campus_id), items in sorted(
        grouped.items(), key=lambda pair: (pair[0][0], -len(pair[1]))
    ):
        user = items[0].user
        call_list = CallList.objects.create(
            campus_id=campus_id, name=f"Lista de {user.username}"[:80]
        )
        call_list.enrollments.set([item.enrollment_id for item in items])
        if user_id not in joined:
            joined.add(user_id)
            CallListMember.objects.create(call_list=call_list, user=user)


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0007_whatsapp_kinds"),
        ("core", "0015_activity_object"),
        ("students", "0012_student_phones"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CallList",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=80, verbose_name="Nombre")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creada el")),
                (
                    "campus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_lists",
                        to="core.campus",
                        verbose_name="Sede",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creada por",
                    ),
                ),
                (
                    "enrollments",
                    models.ManyToManyField(
                        blank=True,
                        related_name="call_lists",
                        to="students.enrollment",
                        verbose_name="Matrículas",
                    ),
                ),
            ],
            options={
                "verbose_name": "sublista de llamadas",
                "verbose_name_plural": "sublistas de llamadas",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="CallListMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Asignado el")),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Asignado por",
                    ),
                ),
                (
                    "call_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="calls.calllist",
                        verbose_name="Sublista",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_membership",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "usuario de sublista",
                "verbose_name_plural": "usuarios de sublistas",
            },
        ),
        migrations.AddConstraint(
            model_name="calllist",
            constraint=models.UniqueConstraint(
                fields=("campus", "name"), name="unique_call_list_name_campus"
            ),
        ),
        migrations.RunPython(assignments_to_lists, migrations.RunPython.noop),
        migrations.DeleteModel(name="CallAssignment"),
    ]
