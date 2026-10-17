from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="full_name",
            field=models.CharField(max_length=180, verbose_name="Nombre completo"),
        ),
        migrations.AddConstraint(
            model_name="student",
            constraint=models.UniqueConstraint(
                fields=("campus", "full_name"),
                name="unique_student_full_name_per_campus",
            ),
        ),
    ]
