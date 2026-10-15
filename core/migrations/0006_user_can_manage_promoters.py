from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_unaccent_extension'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_manage_promoters',
            field=models.BooleanField(default=False, verbose_name='Puede crear promotores'),
        ),
    ]
