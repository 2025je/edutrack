from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_campus_logo"),
    ]

    operations = [
        UnaccentExtension(),
    ]
