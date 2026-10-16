from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_remove_user_first_name_last_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='can_manage_users',
            field=models.BooleanField(default=False, verbose_name='Puede crear y editar usuarios'),
        ),
    ]
