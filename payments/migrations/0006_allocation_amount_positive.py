from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0005_cash_closing"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="paymentallocation",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)), name="allocation_amount_positive"
            ),
        ),
    ]
