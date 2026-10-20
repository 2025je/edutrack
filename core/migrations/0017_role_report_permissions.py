from django.db import migrations


REPORT_PERMISSIONS = {
    "Matrículas": "view_academic_reports",
    "Caja": "view_financial_reports",
    "Gestor de llamadas": "view_call_reports",
}


def grant_report_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for group_name, codename in REPORT_PERMISSIONS.items():
        group = Group.objects.get(name=group_name)
        permission = Permission.objects.get(
            content_type__app_label="core",
            codename=codename,
        )
        group.permissions.add(permission)


def revoke_report_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for group_name, codename in REPORT_PERMISSIONS.items():
        group = Group.objects.get(name=group_name)
        permission = Permission.objects.get(
            content_type__app_label="core",
            codename=codename,
        )
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [("core", "0016_cash_closing")]

    operations = [
        migrations.RunPython(grant_report_permissions, revoke_report_permissions),
    ]
