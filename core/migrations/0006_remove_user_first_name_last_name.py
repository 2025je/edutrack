from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_user_can_manage_users'),
    ]

    operations = [
        migrations.RemoveField(model_name='user', name='first_name'),
        migrations.RemoveField(model_name='user', name='last_name'),
    ]
