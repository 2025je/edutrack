from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from core.models import Campus

phone_validator = RegexValidator(
    r"^\s*9\d{8}(?:\s*,\s*9\d{8})*\s*$",
    "Ingrese uno o más celulares peruanos de 9 dígitos, separados por comas.",
)

class Student(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    full_name = models.CharField("Apellidos y nombres", max_length=180, unique=True)
    document_number = models.CharField("DNI", max_length=20, blank=True)
    phone = models.CharField("Teléfonos", max_length=120, validators=[phone_validator], blank=True)
    active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField("Registrado el", auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "estudiante"
        verbose_name_plural = "estudiantes"
    def __str__(self):
        return self.full_name

class Course(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    name = models.CharField("Curso", max_length=120)
    schedule = models.CharField("Horario", max_length=120, blank=True)
    group = models.CharField("Grupo / aula", max_length=50, blank=True)
    capacity = models.PositiveIntegerField("Capacidad máxima", default=20)
    start_date = models.DateField("Fecha de inicio", default=timezone.localdate)
    enrollment_fee = models.DecimalField("Costo de matrícula", max_digits=10, decimal_places=2, default=0)
    monthly_fee = models.DecimalField("Mensualidad", max_digits=10, decimal_places=2, default=0)
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["name", "schedule", "group"]
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "name", "schedule", "group"],
                name="unique_course_name_schedule_group_per_campus",
            ),
        ]

    def __str__(self):
        detail = " · ".join(x for x in [self.schedule, self.group] if x)
        return f"{self.name} ({detail})" if detail else self.name

class Promoter(models.Model):
    name = models.CharField("Nombre del promotor", max_length=120, unique=True)
    campuses = models.ManyToManyField(Campus, related_name="promoters", verbose_name="Sedes", blank=True)
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "promotor"
        verbose_name_plural = "promotores"

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments", verbose_name="Estudiante")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments", verbose_name="Curso")
    record_code = models.CharField("Código de ficha", max_length=50, blank=True)
    promoter = models.ForeignKey(Promoter, on_delete=models.PROTECT, related_name="enrollments", verbose_name="Promotor", null=True, blank=True)
    enrollment_fee = models.DecimalField("Costo de matrícula", max_digits=10, decimal_places=2, default=0)
    monthly_fee = models.DecimalField("Mensualidad", max_digits=10, decimal_places=2, default=0)
    active = models.BooleanField("Activa", default=True)
    created_at = models.DateTimeField("Creada el", auto_now_add=True)

    class Meta:
        ordering = ["-course__start_date", "student__full_name"]
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"],
                name="unique_student_course_enrollment",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.student_id and self.campus_id and self.student.campus_id != self.campus_id:
            raise ValidationError("El estudiante debe pertenecer a la misma sede de la matrícula.")
        if self.course_id and self.campus_id and self.course.campus_id != self.campus_id:
            raise ValidationError("El curso debe pertenecer a la misma sede de la matrícula.")
        if self.student_id and self.course_id:
            duplicates = Enrollment.objects.filter(student_id=self.student_id, course_id=self.course_id)
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError({"course": "Este estudiante ya está matriculado en este curso."})

    def __str__(self):
        return f"{self.student} — {self.course}"
