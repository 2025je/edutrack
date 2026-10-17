from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import ActivityLog

SKIPPED_PREFIXES = ("/admin/jsi18n", "/__debug__/", "/static/", "/media/")
SKIPPED_URL_NAMES = {"login", "logout"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# (nombre de la ruta) -> (acción, descripción)
URL_ACTIONS = {
    "student-create": (ActivityLog.Action.CREATE, "Registró un estudiante"),
    "student-update": (ActivityLog.Action.UPDATE, "Editó un estudiante"),
    "student-delete": (ActivityLog.Action.DELETE, "Dio de baja a un estudiante"),
    "enrollment-create": (ActivityLog.Action.CREATE, "Registró una matrícula"),
    "enrollment-update": (ActivityLog.Action.UPDATE, "Editó una matrícula"),
    "enrollment-delete": (ActivityLog.Action.DELETE, "Dio de baja una matrícula"),
    "enrollment-excel": (ActivityLog.Action.EXPORT, "Exportó matrículas a Excel"),
    "course-student-export": (ActivityLog.Action.EXPORT, "Exportó alumnos de un curso"),
    "payment-create-for": (ActivityLog.Action.CREATE, "Registró un pago"),
    "payment-update": (ActivityLog.Action.UPDATE, "Editó un pago"),
    "payment-delete": (ActivityLog.Action.DELETE, "Anuló un pago"),
    "calls-note-create": (ActivityLog.Action.CREATE, "Registró una nota de llamada"),
    "calls-note-update": (ActivityLog.Action.UPDATE, "Editó una nota de llamada"),
    "calls-note-delete": (ActivityLog.Action.DELETE, "Eliminó una nota de llamada"),
    "calls-template": (ActivityLog.Action.UPDATE, "Modificó la plantilla de WhatsApp"),
    "calls-assignments": (ActivityLog.Action.UPDATE, "Asignó llamadas"),
    "campus-create": (ActivityLog.Action.CREATE, "Creó una sede"),
    "campus-update": (ActivityLog.Action.UPDATE, "Editó una sede"),
    "campus-flyer-create": (ActivityLog.Action.CREATE, "Subió un volante"),
    "campus-flyer-delete": (ActivityLog.Action.DELETE, "Eliminó un volante"),
    "user-create": (ActivityLog.Action.CREATE, "Creó un usuario"),
    "user-update": (ActivityLog.Action.UPDATE, "Editó un usuario"),
    "schedule-create": (ActivityLog.Action.CREATE, "Creó un horario"),
    "promoter-list": (ActivityLog.Action.UPDATE, "Modificó promotores"),
    "course-list": (ActivityLog.Action.UPDATE, "Modificó cursos"),
    "course-update": (ActivityLog.Action.UPDATE, "Editó un curso"),
    "select-campus": (ActivityLog.Action.OTHER, "Cambió de sede"),
}
# Vistas de solo lectura que sí interesa auditar.
LOGGED_GET_URL_NAMES = {"enrollment-excel", "course-student-export", "payment-receipt"}
GET_ACTIONS = {"payment-receipt": (ActivityLog.Action.OTHER, "Consultó un recibo")}


def client_ip(request):
    return request.META.get("REMOTE_ADDR") or None


def record(request, action, description, user=None, username=""):
    if not request.method:  # login programático (p. ej. force_login) sin petición real
        return
    user = user or getattr(request, "user", None)
    if user is not None and not user.is_authenticated:
        user = None
    campus = None
    campus_id = request.session.get("selected_campus_id") if hasattr(request, "session") else None
    if campus_id:
        from .models import Campus

        campus = Campus.objects.filter(pk=campus_id).first()
    ActivityLog.objects.create(
        user=user,
        username=(user.get_username() if user else username)[:150],
        campus=campus,
        action=action,
        description=description[:255],
        method=request.method[:10],
        path=request.get_full_path()[:500],
        ip_address=client_ip(request),
    )


class ActivityLogMiddleware:
    """Registra las acciones de los usuarios autenticados sin guardar los datos enviados."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self.log(request, response)
        except Exception:  # la auditoría nunca debe romper la petición
            pass
        return response

    def log(self, request, response):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        match = getattr(request, "resolver_match", None)
        url_name = match.url_name if match else None
        if (
            not url_name
            or url_name in SKIPPED_URL_NAMES
            or request.path.startswith(SKIPPED_PREFIXES)
        ):
            return
        if request.method in SAFE_METHODS:
            if url_name not in LOGGED_GET_URL_NAMES or response.status_code >= 400:
                return
            action, label = URL_ACTIONS.get(url_name) or GET_ACTIONS[url_name]
        else:
            # Una respuesta 200 a un POST es un formulario con errores; solo se auditan los éxitos.
            if not 300 <= response.status_code < 400:
                return
            action, label = URL_ACTIONS.get(
                url_name, (ActivityLog.Action.OTHER, f"Acción en «{url_name}»")
            )
        pk = (
            match.kwargs.get("pk")
            or match.kwargs.get("enrollment_id")
            or match.kwargs.get("student_id")
        )
        if pk:
            label = f"{label} (ID {pk})"
        record(request, action, label)


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    record(request, ActivityLog.Action.LOGIN, "Inició sesión", user=user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        record(request, ActivityLog.Action.LOGOUT, "Cerró sesión", user=user)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    if request is not None:
        username = str(credentials.get("username", ""))
        record(
            request, ActivityLog.Action.LOGIN_FAILED, "Intento de acceso fallido", username=username
        )
