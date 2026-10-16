from django.db import migrations


def set_unassigned_group(apps, schema_editor):
    Course = apps.get_model("students", "Course")
    Course.objects.filter(name="POR ASIGNAR", schedule="PENDIENTE DE ASIGNACION").update(
        group="PENDIENTE DE ASIGNACION"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0015_fees_greater_than_zero"),
    ]

    operations = [
        migrations.RunPython(set_unassigned_group, migrations.RunPython.noop),
    ]
