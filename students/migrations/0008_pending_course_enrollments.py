import django.db.models.deletion
from django.db import migrations, models


def remove_unassigned_course(apps, schema_editor):
    Course = apps.get_model("students", "Course")
    Enrollment = apps.get_model("students", "Enrollment")
    Schedule = apps.get_model("students", "Schedule")
    database = schema_editor.connection.alias

    unassigned_courses = Course.objects.using(database).filter(name="SIN CURSO")
    unassigned_ids = list(unassigned_courses.values_list("pk", flat=True))
    Enrollment.objects.using(database).filter(course_id__in=unassigned_ids).update(course=None)
    unassigned_courses.delete()
    if not Course.objects.using(database).filter(schedule="-").exists():
        Schedule.objects.using(database).filter(name="-").delete()


def restore_unassigned_course(apps, schema_editor):
    Course = apps.get_model("students", "Course")
    Enrollment = apps.get_model("students", "Enrollment")
    database = schema_editor.connection.alias
    campus_ids = Enrollment.objects.using(database).filter(course__isnull=True).values_list(
        "campus_id", flat=True
    ).distinct()
    for campus_id in campus_ids:
        course, _ = Course.objects.using(database).get_or_create(
            campus_id=campus_id,
            name="SIN CURSO",
            schedule="-",
            group="-",
            defaults={
                "capacity": 1,
                "start_date": None,
                "enrollment_fee": 0,
                "monthly_fee": 0,
                "active": True,
            },
        )
        Enrollment.objects.using(database).filter(
            campus_id=campus_id, course__isnull=True
        ).update(course_id=course.pk)


class Migration(migrations.Migration):
    dependencies = [("students", "0007_rename_unassigned_course")]

    operations = [
        migrations.AlterField(
            model_name="enrollment",
            name="course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="enrollments",
                to="students.course",
                verbose_name="Curso",
            ),
        ),
        migrations.RunPython(remove_unassigned_course, restore_unassigned_course),
        migrations.AddConstraint(
            model_name="enrollment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("student__isnull", False), ("course__isnull", False), _connector="OR"
                ),
                name="enrollment_requires_student_or_course",
            ),
        ),
    ]
