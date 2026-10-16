from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_user_can_manage_campuses'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_manage_users',
            field=models.BooleanField(default=False, verbose_name='Puede crear usuarios'),
        ),
    ]
