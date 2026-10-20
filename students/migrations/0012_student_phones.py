from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def migrate_legacy_phones(apps, schema_editor):
    Student = apps.get_model("students", "Student")
    StudentPhone = apps.get_model("students", "StudentPhone")
    database = schema_editor.connection.alias
    for student in Student.objects.using(database).only("id", "phone").iterator():
        numbers = dict.fromkeys(
            number.strip() for number in (student.phone or "").split(",") if number.strip()
        )
        StudentPhone.objects.using(database).bulk_create(
            [
                StudentPhone(student_id=student.pk, number=number)
                for number in numbers
            ],
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0011_unique_enrollment_student_course"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="phone",
            field=models.CharField(
                max_length=1000,
                validators=[
                    django.core.validators.RegexValidator(
                        r"^\s*9\d{8}(?:\s*,\s*9\d{8})*\s*$",
                        "Ingrese uno o más celulares peruanos de 9 dígitos, separados por comas.",
                    )
                ],
                verbose_name="Teléfonos",
            ),
        ),
        migrations.CreateModel(
            name="StudentPhone",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "number",
                    models.CharField(
                        max_length=20,
                        validators=[
                            django.core.validators.RegexValidator(
                                r"^\s*9\d{8}\s*$",
                                "Ingrese un celular peruano de 9 dígitos que empiece con 9.",
                            )
                        ],
                        verbose_name="Teléfono",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="phones",
                        to="students.student",
                        verbose_name="Estudiante",
                    ),
                ),
            ],
            options={
                "verbose_name": "teléfono de estudiante",
                "verbose_name_plural": "teléfonos de estudiantes",
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="studentphone",
            constraint=models.UniqueConstraint(
                fields=("student", "number"), name="unique_student_phone"
            ),
        ),
        migrations.RunPython(migrate_legacy_phones, migrations.RunPython.noop),
    ]
