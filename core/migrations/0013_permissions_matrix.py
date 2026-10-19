from django.db import migrations

STUDENTS_VIEW = ["students.view_student", "students.view_course", "students.view_enrollment"]

# Solo las celdas ✅ de la matriz; los 🔒 se conceden aparte desde el admin.
GROUPS = {
    "Matrículas": [
        *STUDENTS_VIEW,
        "students.add_student",
        "students.change_student",
        "students.add_enrollment",
        "students.change_enrollment",
    ],
    "Caja": [
        "students.view_course",
        "payments.view_payment",
        "payments.add_payment",
        "payments.view_installment",
    ],
    "Gestor de llamadas": ["calls.view_callnote", "calls.add_callnote"],
    "Asignador de llamadas": ["calls.view_callnote", "core.assign_calls"],
    "Supervisor de campus": [
        *STUDENTS_VIEW,
        "students.view_promoter",
        "calls.view_callnote",
        "core.view_all_calls",
        "core.view_academic_reports",
    ],
    "Administrador general": [
        *STUDENTS_VIEW,
        "students.view_promoter",
        "payments.view_payment",
        "payments.add_payment",
        "payments.view_installment",
        "calls.view_callnote",
        "core.view_all_calls",
        "core.view_academic_reports",
        "core.view_call_reports",
        "core.view_financial_reports",
        "core.export_reports",
        "core.view_user",
        "core.manage_user_access",
        "core.view_campus",
        "core.add_campus",
        "core.change_campus",
        "auth.view_group",
        "auth.add_group",
        "auth.change_group",
        "auth.view_permission",
    ],
}

RENAMES = {
    "Gestor llamadas": "Gestor de llamadas",
    "Asignador llamadas": "Asignador de llamadas",
    "Supervisor": "Supervisor de campus",
    "Administrador": "Administrador general",
}

OBSOLETE = [
    "manage_students",
    "register_payments",
    "manage_promoters",
    "manage_calls",
    "manage_campuses",
    "manage_users",
]


def apply_matrix(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    for label in ("core", "students", "payments", "calls", "auth"):
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for old, new in RENAMES.items():
        if not Group.objects.filter(name=new).exists():
            Group.objects.filter(name=old).update(name=new)

    for name, perms in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        found = []
        for perm in perms:
            app_label, codename = perm.split(".")
            found.append(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        group.permissions.set(found)

    Permission.objects.filter(content_type__app_label="core", codename__in=OBSOLETE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_role_groups"),
        ("students", "0005_ficha_code_integer"),
        ("payments", "0002_payment_voucher"),
        ("calls", "0005_call_assignments"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="featureaccess",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": [
                    ("deactivate_student", "Desactivar un estudiante"),
                    ("deactivate_enrollment", "Desactivar una matrícula"),
                    ("change_enrollment_course", "Cambiar el curso asociado a una matrícula"),
                    ("void_payment", "Anular un pago conservando su historial"),
                    ("edit_call_notes", "Modificar notas de llamadas existentes"),
                    ("assign_calls", "Asignar llamadas a gestores"),
                    ("view_all_calls", "Consultar todas las llamadas autorizadas del campus"),
                    ("view_financial_reports", "Consultar reportes financieros"),
                    ("view_academic_reports", "Consultar reportes académicos"),
                    ("view_call_reports", "Consultar reportes de llamadas"),
                    ("export_reports", "Exportar reportes autorizados a Excel"),
                    ("manage_user_access", "Administrar usuarios, grupos y permisos"),
                ],
            },
        ),
        migrations.RunPython(apply_matrix, migrations.RunPython.noop),
    ]
