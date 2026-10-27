import mimetypes
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse

from .campus import available_campuses


def login_client(request):
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "-"


class ThrottledAuthenticationForm(AuthenticationForm):
    """Bloquea temporalmente al par IP + usuario tras varios intentos fallidos."""

    def _key(self):
        username = (self.data.get("username") or "").strip().lower()
        return f"login-fail:{login_client(self.request)}:{username}"

    def clean(self):
        key = self._key()
        if cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
            minutes = max(settings.LOGIN_LOCKOUT_SECONDS // 60, 1)
            raise ValidationError(
                f"Demasiados intentos fallidos. Espera {minutes} minutos e inténtalo de nuevo.",
                code="locked",
            )
        try:
            cleaned = super().clean()
        except ValidationError:
            cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)
            raise
        cache.delete(key)
        return cleaned


def health(request):
    """Comprobación de estado para Docker y monitoreo (sin autenticación)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "database": False}, status=503)
    return JsonResponse({"status": "ok"})


PUBLIC_MEDIA_PREFIXES = ("campus_logos/", "campus_flyers/")


def _can_access_media(user, name):
    if name.startswith(PUBLIC_MEDIA_PREFIXES):
        return True
    from payments.models import Payment
    from students.models import Ficha

    campuses = available_campuses(user)
    if name.startswith("vouchers/"):
        return Payment.objects.filter(voucher=name, campus__in=campuses).exists()
    if name.startswith("fichas/"):
        return Ficha.objects.filter(image=name, campus__in=campuses).exists()
    return user.is_superuser


@login_required
def protected_media(request, path):
    """Entrega un archivo subido solo a usuarios con acceso a su sede."""
    name = PurePosixPath(path)
    if name.is_absolute() or ".." in name.parts:
        raise Http404
    name = name.as_posix()
    if not _can_access_media(request.user, name):
        raise Http404

    if settings.DEBUG:
        full_path = settings.MEDIA_ROOT / name
        if not full_path.is_file():
            raise Http404
        return FileResponse(open(full_path, "rb"))

    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    response = HttpResponse(content_type=content_type)
    response["X-Accel-Redirect"] = f"/_protected_media/{name}"
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
