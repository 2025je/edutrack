from django.contrib.auth.models import Group, Permission

from .models import User

# Atajos de prueba: cada nombre agrupa los permisos nativos que antes daba un booleano.
LEGACY_FLAGS = {
    "manage_students": [
        "students.view_student",
        "students.add_student",
        "students.change_student",
        "students.view_enrollment",
        "students.add_enrollment",
        "students.change_enrollment",
        "core.deactivate_student",
        "core.deactivate_enrollment",
        "core.change_enrollment_course",
        "core.view_academic_reports",
        "core.export_reports",
    ],
    "register_payments": [
        "payments.view_payment",
        "payments.add_payment",
        "payments.change_payment",
        "core.view_pending_balances",
        "core.void_payment",
        "core.view_financial_reports",
    ],
    "manage_promoters": [
        "students.view_course",
        "students.add_course",
        "students.change_course",
        "students.view_promoter",
        "students.add_promoter",
    ],
    "manage_calls": ["calls.view_callnote", "calls.add_callnote"],
    "edit_call_notes": ["core.edit_call_notes"],
    "assign_calls": ["core.assign_calls", "core.view_all_calls"],
    "manage_campuses": ["core.view_campus", "core.add_campus", "core.change_campus"],
    "manage_users": ["core.view_user", "core.manage_user_access"],
}


def _resolve(name):
    return LEGACY_FLAGS.get(name, [name])


def feature_group(name):
    """Grupo de Django con los permisos del atajo `name` (o de un `app.codename`)."""
    group, created = Group.objects.get_or_create(name=f"test_{name}")
    if created:
        for perm in _resolve(name):
            app_label, codename = perm.split(".")
            group.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
    return group


def _clear_cache(user):
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        user.__dict__.pop(attr, None)


def grant(user, *names):
    user.groups.add(*(feature_group(n) for n in names))
    _clear_cache(user)


def revoke(user, *names):
    user.groups.remove(*(feature_group(n) for n in names))
    _clear_cache(user)


def create_user(*args, **kwargs):
    """create_user que acepta `manage_x=True` y asigna los permisos vía grupos."""
    names = [name for name in LEGACY_FLAGS if kwargs.pop(name, False)]
    user = User.objects.create_user(*args, **kwargs)
    grant(user, *names)
    return user
