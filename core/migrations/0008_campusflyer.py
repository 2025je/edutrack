import core.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_alter_user_can_manage_users'),
    ]

    operations = [
        migrations.CreateModel(
            name='CampusFlyer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120, verbose_name='Título')),
                ('file', models.FileField(upload_to='campus_flyers/', validators=[core.models.validate_flyer], verbose_name='Archivo')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name='Subido el')),
                ('campus', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='flyers', to='core.campus')),
            ],
            options={
                'verbose_name': 'volante',
                'verbose_name_plural': 'volantes',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
