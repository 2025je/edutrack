from django.db import migrations

SENSITIVE_PERMISSIONS = {
    "Supervisor de campus": [
        "deactivate_student",
        "deactivate_enrollment",
        "change_enrollment_course",
        "edit_call_notes",
    ],
    "Administrador general": ["void_payment"],
}


def permissions_by_group(apps):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for group_name, codenames in SENSITIVE_PERMISSIONS.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            continue
        yield group, Permission.objects.filter(
            content_type__app_label="core", codename__in=codenames
        )


def grant(apps, schema_editor):
    for group, permissions in permissions_by_group(apps):
        group.permissions.add(*permissions)


def revoke(apps, schema_editor):
    for group, permissions in permissions_by_group(apps):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [("core", "0020_remove_callassignment_permissions")]

    operations = [migrations.RunPython(grant, revoke)]
