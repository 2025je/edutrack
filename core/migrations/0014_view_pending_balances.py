from django.db import migrations

# Caja conserva ambos accesos (pagos y saldos); el supervisor lo recibe aparte (🔒).
GROUPS = ["Caja", "Administrador general"]


def add_permission(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    new = Permission.objects.get(content_type__app_label="core", codename="view_pending_balances")
    old = Permission.objects.filter(
        content_type__app_label="payments", codename="view_installment"
    ).first()
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.add(new)
        if old:
            group.permissions.remove(old)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_permissions_matrix"),
        ("payments", "0002_payment_voucher"),
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
                    ("view_pending_balances", "Consultar cuotas y saldos pendientes"),
                    ("view_academic_reports", "Consultar reportes académicos"),
                    ("view_call_reports", "Consultar reportes de llamadas"),
                    ("export_reports", "Exportar reportes autorizados a Excel"),
                    ("manage_user_access", "Administrar usuarios, grupos y permisos"),
                ],
            },
        ),
        migrations.RunPython(add_permission, migrations.RunPython.noop),
    ]
