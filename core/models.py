from django.contrib.auth.models import AbstractUser
from django.db import models


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
    can_manage_users = models.BooleanField("Puede crear usuarios", default=False)
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
