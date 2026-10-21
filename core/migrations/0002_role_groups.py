from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUPS = {
    "Matrículas": [
        "core.view_academic_reports",
        "students.add_enrollment",
        "students.add_student",
        "students.change_enrollment",
        "students.change_student",
        "students.view_course",
        "students.view_enrollment",
        "students.view_student",
    ],
    "Caja": [
        "core.view_financial_reports",
        "core.view_pending_balances",
        "payments.add_payment",
        "payments.view_payment",
        "students.view_course",
    ],
    "Gestor de llamadas": [
        "calls.add_callnote",
        "calls.view_callnote",
        "core.view_call_reports",
    ],
    "Asignador de llamadas": [
        "calls.view_callnote",
        "core.assign_calls",
    ],
    "Supervisor de campus": [
        "calls.view_callnote",
        "core.change_enrollment_course",
        "core.deactivate_enrollment",
        "core.deactivate_student",
        "core.edit_call_notes",
        "core.view_academic_reports",
        "core.view_all_calls",
        "students.view_course",
        "students.view_enrollment",
        "students.view_promoter",
        "students.view_student",
    ],
    # Nunca incluye Caja: quien cobra no anula sus propios recibos (core.void_payment).
    "Administrador general": [
        "auth.add_group",
        "auth.change_group",
        "auth.view_group",
        "auth.view_permission",
        "calls.view_callnote",
        "core.add_campus",
        "core.change_campus",
        "core.export_reports",
        "core.manage_user_access",
        "core.view_academic_reports",
        "core.view_all_calls",
        "core.view_call_reports",
        "core.view_campus",
        "core.view_financial_reports",
        "core.view_pending_balances",
        "core.view_user",
        "core.void_payment",
        "payments.add_payment",
        "payments.view_payment",
        "students.view_course",
        "students.view_enrollment",
        "students.view_promoter",
        "students.view_student",
    ],
    "Gestor de catálogo académico": [
        "students.add_course",
        "students.add_promoter",
        "students.change_course",
        "students.change_promoter",
        "students.view_course",
        "students.view_promoter",
    ],
}


def create_role_groups(apps, schema_editor):
    # Los permisos se crean normalmente en post_migrate; aquí se necesitan antes.
    for label in sorted({perm.split(".")[0] for perms in GROUPS.values() for perm in perms}):
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, perms in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        for perm in perms:
            app_label, codename = perm.split(".")
            group.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )


def delete_role_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0001_initial"),
        ("students", "0001_initial"),
        ("payments", "0001_initial"),
        ("calls", "0002_initial"),
    ]

    operations = [migrations.RunPython(create_role_groups, delete_role_groups)]
