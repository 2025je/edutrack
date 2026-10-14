import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0005_course_unique_identity_per_campus"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="document_number",
            field=models.CharField(blank=True, max_length=20, verbose_name="DNI"),
        ),
        migrations.AlterField(
            model_name="student",
            name="phone",
            field=models.CharField(
                blank=True,
                max_length=120,
                validators=[
                    django.core.validators.RegexValidator(
                        "^\\s*9\\d{8}(?:\\s*,\\s*9\\d{8})*\\s*$",
                        "Ingrese uno o más celulares peruanos de 9 dígitos, separados por comas.",
                    )
                ],
                verbose_name="Teléfonos",
            ),
        ),
    ]