from django.db import migrations

GROUP_NAME = "Gestor de catálogo académico"
PERMISSIONS = [
    "students.view_course",
    "students.add_course",
    "students.change_course",
    "students.view_promoter",
    "students.add_promoter",
    "students.change_promoter",
]


def create_group(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    for label in ("students",):
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.set(
        Permission.objects.get(content_type__app_label=perm.split(".")[0], codename=perm.split(".")[1])
        for perm in PERMISSIONS
    )


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_role_report_permissions"),
        ("students", "0012_student_phones"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
