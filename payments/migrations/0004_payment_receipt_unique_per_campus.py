import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0003_alter_payment_receipt_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="receipt_number",
            field=models.CharField(
                max_length=40,
                validators=[
                    django.core.validators.RegexValidator(
                        "^(?:\\d+|[A-Z]\\d+)$",
                        "Ingrese solo números o una letra mayúscula seguida de números, por ejemplo: 100 o D100.",
                    )
                ],
                verbose_name="N.º de recibo",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("campus", "receipt_number"),
                name="unique_payment_receipt_number_per_campus",
            ),
        ),
    ]
