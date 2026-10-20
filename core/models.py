import os

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

MAX_FLYER_SIZE = 10 * 1024 * 1024


class Campus(models.Model):
    name = models.CharField("Nombre de la sede", max_length=120, unique=True)
    active = models.BooleanField("Activa", default=True)
    address = models.CharField("Dirección", max_length=200, blank=True)
    logo = models.ImageField("Logo", upload_to="campus_logos/", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "sede"
        verbose_name_plural = "sedes"

    def __str__(self):
        return self.name


FLYER_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}


def validate_flyer(file):
    extension = os.path.splitext(file.name)[1].lower()
    if extension not in FLYER_SIGNATURES:
        raise ValidationError("Solo se permiten archivos PDF, PNG, JPG o WEBP.")
    if file.size > MAX_FLYER_SIZE:
        raise ValidationError("El archivo no puede superar los 10 MB.")
    header = file.read(12)
    file.seek(0)
    valid = header.startswith(FLYER_SIGNATURES[extension])
    if extension == ".webp":
        valid = valid and header[8:12] == b"WEBP"
    if not valid:
        raise ValidationError("El contenido del archivo no corresponde a su extensión.")


class CampusFlyer(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.CASCADE, related_name="flyers")
    title = models.CharField("Título", max_length=120)
    file = models.FileField("Archivo", upload_to="campus_flyers/", validators=[validate_flyer])
    uploaded_at = models.DateTimeField("Subido el", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "volante"
        verbose_name_plural = "volantes"

    def __str__(self):
        return f"{self.title} ({self.campus})"

    @property
    def is_image(self):
        return not self.file.name.lower().endswith(".pdf")


class FeatureAccess(models.Model):
    """Sin tabla: solo declara los permisos nativos de Django que se asignan vía grupos."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
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
            ("close_cash", "Cerrar la caja del día"),
            ("export_reports", "Exportar reportes autorizados a Excel"),
            ("manage_user_access", "Administrar usuarios, grupos y permisos"),
        ]


class User(AbstractUser):
    campuses = models.ManyToManyField(
        Campus, blank=True, related_name="users", verbose_name="Sedes asignadas"
    )
    onboarding_completed_at = models.DateTimeField(
        "Guía inicial vista el", null=True, blank=True, editable=False
    )

    # Los usuarios se identifican solo por su nombre de usuario.
    first_name = None
    last_name = None

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def get_full_name(self):
        return self.username

    def get_short_name(self):
        return self.username

    def can_access_campus(self, campus):
        return self.is_superuser or self.campuses.filter(pk=campus.pk, active=True).exists()


class ActivityLog(models.Model):
    """Registro de auditoría de lo que hacen los usuarios en el sistema."""

    class Action(models.TextChoices):
        LOGIN = "login", "Inicio de sesión"
        LOGIN_FAILED = "login_failed", "Intento de acceso fallido"
        LOGOUT = "logout", "Cierre de sesión"
        CREATE = "create", "Creación"
        UPDATE = "update", "Edición"
        DELETE = "delete", "Eliminación"
        EXPORT = "export", "Exportación"
        OTHER = "other", "Otra acción"

    created_at = models.DateTimeField("Fecha y hora", auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        "core.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
        verbose_name="Usuario",
    )
    username = models.CharField("Usuario (texto)", max_length=150, blank=True)
    campus = models.ForeignKey(
        Campus, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Sede"
    )
    action = models.CharField("Acción", max_length=20, choices=Action.choices, db_index=True)
    description = models.CharField("Descripción", max_length=255)
    method = models.CharField("Método", max_length=10, blank=True)
    path = models.CharField("Ruta", max_length=500, blank=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    object_type = models.CharField("Tipo de objeto", max_length=20, blank=True)
    object_id = models.PositiveIntegerField("ID del objeto", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["object_type", "object_id"])]
        verbose_name = "registro de actividad"
        verbose_name_plural = "registro de actividades"

    def __str__(self):
        return (
            f"{self.created_at:%Y-%m-%d %H:%M} · {self.username or 'anónimo'} · {self.description}"
        )
