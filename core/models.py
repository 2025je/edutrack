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


class User(AbstractUser):
    campuses = models.ManyToManyField(
        Campus, blank=True, related_name="users", verbose_name="Sedes asignadas"
    )
    can_manage_students = models.BooleanField("Puede registrar alumnos y matrículas", default=False)
    can_register_payments = models.BooleanField("Puede registrar pagos", default=False)
    can_manage_promoters = models.BooleanField("Puede crear promotores y cursos", default=False)
    can_manage_calls = models.BooleanField("Puede acceder a llamadas", default=False)
    can_manage_campuses = models.BooleanField(
        "Puede crear y editar sedes y asignarlas a usuarios", default=False
    )
    can_manage_users = models.BooleanField("Puede crear y editar usuarios", default=False)
    can_edit_call_notes = models.BooleanField(
        "Puede editar y eliminar el historial de llamadas", default=False
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
