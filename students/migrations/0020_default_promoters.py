from django.db import migrations


def create_default_promoters(apps, schema_editor):
    Campus = apps.get_model("core", "Campus")
    Promoter = apps.get_model("students", "Promoter")
    for name in ("PARTICULAR", "NN"):
        promoter, _ = Promoter.objects.get_or_create(name=name)
        promoter.campuses.add(*Campus.objects.all())


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0019_has_record_label"),
    ]

    operations = [
        migrations.RunPython(create_default_promoters, migrations.RunPython.noop),
    ]
