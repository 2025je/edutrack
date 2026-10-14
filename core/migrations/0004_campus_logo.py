from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_remove_user_is_cashier"),
    ]

    operations = [
        migrations.AddField(
            model_name="campus",
            name="logo",
            field=models.ImageField(blank=True, upload_to="campus_logos/", verbose_name="Logo"),
        ),
    ]