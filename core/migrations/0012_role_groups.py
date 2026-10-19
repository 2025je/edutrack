from django.db import migrations

ALL = [
    "manage_students",
    "register_payments",
    "manage_promoters",
    "manage_calls",
    "edit_call_notes",
    "assign_calls",
    "manage_campuses",
    "manage_users",
]

GROUPS = {
    "Matrículas": ["manage_students"],
    "Caja": ["register_payments"],
    "Gestor llamadas": ["manage_calls"],
    "Asignador llamadas": ["manage_calls", "assign_calls"],
    "Supervisor": [
        "manage_students",
        "register_payments",
        "manage_promoters",
        "manage_calls",
        "edit_call_notes",
        "assign_calls",
    ],
    "Administrador": ALL,
}

# Grupos granulares creados en 0011 y el grupo de rol que los reemplaza.
OLD_TO_NEW = {
    "Alumnos y matrículas": "Matrículas",
    "Pagos": "Caja",
    "Llamadas": "Gestor llamadas",
    "Asignar llamadas": "Asignador llamadas",
    "Promotores y cursos": "Supervisor",
    "Editar historial de llamadas": "Supervisor",
    "Sedes": "Administrador",
    "Usuarios": "Administrador",
}


def create_role_groups(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    groups = {}
    for name, codenames in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(
            Permission.objects.filter(content_type__app_label="core", codename__in=codenames)
        )
        groups[name] = group

    for old_name, new_name in OLD_TO_NEW.items():
        old = Group.objects.filter(name=old_name).first()
        if old is None:
            continue
        for user in old.user_set.all():
            user.groups.add(groups[new_name])
        old.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_feature_permissions"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(create_role_groups, migrations.RunPython.noop)]
