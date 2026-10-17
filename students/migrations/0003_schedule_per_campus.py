from django.db import migrations, models
import django.db.models.deletion


def assign_schedules_to_campuses(apps, schema_editor):
    Campus = apps.get_model("core", "Campus")
    Schedule = apps.get_model("students", "Schedule")
    database = schema_editor.connection.alias
    campus_ids = list(Campus.objects.using(database).values_list("pk", flat=True))
    names = list(
        Schedule.objects.using(database)
        .values_list("name", flat=True)
        .order_by("pk")
    )
    names = list(dict.fromkeys(name.strip().upper() for name in names if name.strip()))
    Schedule.objects.using(database).all().delete()
    Schedule.objects.using(database).bulk_create(
        Schedule(campus_id=campus_id, name=name)
        for campus_id in campus_ids
        for name in names
    )


def restore_global_schedules(apps, schema_editor):
    Schedule = apps.get_model("students", "Schedule")
    database = schema_editor.connection.alias
    schedules = list(Schedule.objects.using(database).order_by("pk"))
    retained = set()
    for schedule in schedules:
        normalized_name = schedule.name.upper()
        if normalized_name in retained:
            schedule.delete(using=database)
            continue
        retained.add(normalized_name)
        Schedule.objects.using(database).filter(pk=schedule.pk).update(campus_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("students", "0002_student_unique_name_per_campus"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schedule",
            name="name",
            field=models.CharField(max_length=120, verbose_name="Horario"),
        ),
        migrations.AddField(
            model_name="schedule",
            name="campus",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="core.campus",
                verbose_name="Sede",
            ),
        ),
        migrations.RunPython(assign_schedules_to_campuses, restore_global_schedules),
        migrations.AlterField(
            model_name="schedule",
            name="campus",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="core.campus",
                verbose_name="Sede",
            ),
        ),
        migrations.AddConstraint(
            model_name="schedule",
            constraint=models.UniqueConstraint(
                fields=("campus", "name"),
                name="unique_schedule_name_per_campus",
            ),
        ),
    ]
