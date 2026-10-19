from django.shortcuts import redirect
from .models import Campus


def available_campuses(user):
    """Sedes activas que el usuario está autorizado a utilizar."""
    qs = Campus.objects.filter(active=True)
    if user.is_superuser:
        return qs
    return qs.filter(users=user)


def get_selected_campus(request):
    """Obtiene y valida la sede guardada en la sesión del usuario."""
    campus_id = request.session.get("selected_campus_id")
    if not campus_id:
        return None
    campus = available_campuses(request.user).filter(pk=campus_id).first()
    if campus is None:
        request.session.pop("selected_campus_id", None)
    return campus


class SelectedCampusRequiredMixin:
    """Exige que el usuario haya elegido una sede y valida su autorización."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if get_selected_campus(request) is None:
            return redirect("select-campus")
        return super().dispatch(request, *args, **kwargs)

    @property
    def selected_campus(self):
        return get_selected_campus(self.request)


class FeaturePermissionMixin:
    """Exige permisos nativos de Django (`app.codename`) para acceder a la vista.

    `required_permission` puede ser un texto o una tupla (se exigen todos).
    `method_permissions` permite exigir otro permiso según el método HTTP.
    """

    required_permission = None
    method_permissions = {}

    def get_required_permissions(self, request):
        required = self.method_permissions.get(request.method, self.required_permission)
        if not required:
            return ()
        return (required,) if isinstance(required, str) else tuple(required)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not all(request.user.has_perm(p) for p in self.get_required_permissions(request)):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("No tienes permiso para acceder a esta sección.")
        return super().dispatch(request, *args, **kwargs)


def users_with_perm(perm):
    """Usuarios activos con el permiso `app.codename`, directo o por grupo."""
    from django.db.models import Q

    from .models import User

    app_label, codename = perm.split(".")
    return User.objects.filter(
        Q(
            user_permissions__codename=codename,
            user_permissions__content_type__app_label=app_label,
        )
        | Q(
            groups__permissions__codename=codename,
            groups__permissions__content_type__app_label=app_label,
        ),
        is_active=True,
    ).distinct()
