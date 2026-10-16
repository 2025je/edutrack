from django.db import migrations


def create_unassigned_courses(apps, schema_editor):
    Campus = apps.get_model("core", "Campus")
    Course = apps.get_model("students", "Course")
    Schedule = apps.get_model("students", "Schedule")
    Schedule.objects.get_or_create(name="PENDIENTE DE ASIGNACION")
    for campus in Campus.objects.all():
        Course.objects.get_or_create(
            campus=campus,
            name="POR ASIGNAR",
            schedule="PENDIENTE DE ASIGNACION",
            group="1",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_rename_can_manage_promoters_label"),
        ("students", "0013_student_first_name_student_last_name_and_more"),
    ]

    operations = [
        migrations.RunPython(create_unassigned_courses, migrations.RunPython.noop),
    ]
