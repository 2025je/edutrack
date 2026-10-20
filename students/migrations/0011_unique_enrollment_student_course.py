from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0010_performance_indexes"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="enrollment",
            constraint=models.UniqueConstraint(
                condition=models.Q(student__isnull=False, course__isnull=False),
                fields=("student", "course"),
                name="unique_enrollment_student_course",
            ),
        ),
    ]
