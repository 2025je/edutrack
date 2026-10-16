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

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def can_access_campus(self, campus):
        return self.is_superuser or self.campuses.filter(pk=campus.pk, active=True).exists()
