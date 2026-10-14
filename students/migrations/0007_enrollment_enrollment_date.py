from django.db import migrations, models
from django.utils import timezone


def copy_created_date_to_enrollment_date(apps, schema_editor):
    Enrollment = apps.get_model("students", "Enrollment")
    for enrollment in Enrollment.objects.only("pk", "created_at").iterator():
        enrollment.enrollment_date = timezone.localtime(enrollment.created_at).date()
        enrollment.save(update_fields=["enrollment_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0006_student_multiple_phones_and_dni_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="enrollment_date",
            field=models.DateField(blank=True, null=True, verbose_name="Fecha de matrícula"),
        ),
        migrations.RunPython(copy_created_date_to_enrollment_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="enrollment",
            name="enrollment_date",
            field=models.DateField(default=timezone.localdate, verbose_name="Fecha de matrícula"),
        ),
    ]