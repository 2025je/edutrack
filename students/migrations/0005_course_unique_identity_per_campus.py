from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0004_enrollment_record_code_promoter_enrollment_promoter"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="course",
            constraint=models.UniqueConstraint(
                fields=("campus", "name", "schedule", "group"),
                name="unique_course_name_schedule_group_per_campus",
            ),
        ),
    ]