from django.db import migrations

OLD_COURSE, OLD_SCHEDULE = "POR ASIGNAR", "PENDIENTE DE ASIGNACION"
NEW_COURSE, NEW_SCHEDULE = "SIN CURSO", "-"


def rename(apps, old_course, old_schedule, new_course, new_schedule):
    Course = apps.get_model("students", "Course")
    Schedule = apps.get_model("students", "Schedule")
    Course.objects.filter(name=old_course, schedule=old_schedule).update(
        name=new_course, schedule=new_schedule, group=new_schedule
    )
    Schedule.objects.filter(name=old_schedule).update(name=new_schedule)


def forwards(apps, schema_editor):
    rename(apps, OLD_COURSE, OLD_SCHEDULE, NEW_COURSE, NEW_SCHEDULE)


def backwards(apps, schema_editor):
    rename(apps, NEW_COURSE, NEW_SCHEDULE, OLD_COURSE, OLD_SCHEDULE)


class Migration(migrations.Migration):
    dependencies = [("students", "0006_enrollment_optional_student")]

    operations = [migrations.RunPython(forwards, backwards)]
