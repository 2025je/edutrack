from django.core.exceptions import PermissionDenied
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
    """Bloquea vistas según permisos operativos del usuario."""
    permission_field = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_superuser and self.permission_field and not getattr(request.user, self.permission_field, False):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permiso para acceder a esta sección.")
        return super().dispatch(request, *args, **kwargs)
