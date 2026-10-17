from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone
from core.models import Campus

positive_amount_validator = MinValueValidator(Decimal("0.01"), "El valor debe ser mayor a 0.")

phone_validator = RegexValidator(
    r"^\s*9\d{8}(?:\s*,\s*9\d{8})*\s*$",
    "Ingrese uno o más celulares peruanos de 9 dígitos, separados por comas.",
)

record_code_validator = RegexValidator(
    r"^\d*$",
    "Ingrese solo números en el código de ficha.",
)

MAX_FICHA_IMAGE_SIZE = 10 * 1024 * 1024
DUPLICATE_FICHA_MESSAGE = "Este código de ficha ya está registrado en la misma fecha de matrícula."

UNASSIGNED_COURSE_NAME = "POR ASIGNAR"
UNASSIGNED_SCHEDULE_NAME = "PENDIENTE DE ASIGNACION"


DEFAULT_PROMOTER_NAMES = ("PARTICULAR", "NN")
DEFAULT_SCHEDULE_NAMES = (
    "SÁBADOS DE 8AM A 11AM",
    "SÁBADOS DE 11AM A 2PM",
    UNASSIGNED_SCHEDULE_NAME,
)


def ensure_default_promoters(campus):
    for name in DEFAULT_PROMOTER_NAMES:
        promoter, _ = Promoter.objects.get_or_create(name=name)
        promoter.campuses.add(campus)


def ensure_default_schedules(campus):
    for name in DEFAULT_SCHEDULE_NAMES:
        Schedule.objects.get_or_create(campus=campus, name=name)


def ensure_unassigned_course(campus):
    schedule, _ = Schedule.objects.get_or_create(campus=campus, name=UNASSIGNED_SCHEDULE_NAME)
    course, _ = Course.objects.get_or_create(
        campus=campus,
        name=UNASSIGNED_COURSE_NAME,
        schedule=UNASSIGNED_SCHEDULE_NAME,
        group=UNASSIGNED_SCHEDULE_NAME,
        defaults={
            "start_date": None,
            "capacity": None,
            "enrollment_fee": None,
            "monthly_fee": None,
        },
    )
    return course, schedule


class Student(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    full_name = models.CharField("Nombre completo", max_length=180)
    last_name = models.CharField("Apellidos", max_length=120, blank=True)
    first_name = models.CharField("Nombres", max_length=120, blank=True)
    document_number = models.CharField("DNI", max_length=20, blank=True)
    phone = models.CharField("Teléfonos", max_length=120, validators=[phone_validator])
    active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField("Registrado el", auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "estudiante"
        verbose_name_plural = "estudiantes"
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "full_name"],
                name="unique_student_full_name_per_campus",
            ),
        ]

    def save(self, *args, **kwargs):
        self.full_name = self.full_name.upper()
        self.last_name = self.last_name.upper()
        self.first_name = self.first_name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class Course(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    name = models.CharField("Curso", max_length=120)
    schedule = models.CharField("Horario", max_length=120)
    group = models.CharField("Grupo / aula", max_length=50, default="1")
    capacity = models.PositiveIntegerField("Capacidad máxima", default=20, null=True, blank=True)
    start_date = models.DateField(
        "Fecha de inicio", default=timezone.localdate, null=True, blank=True
    )
    enrollment_fee = models.DecimalField(
        "Costo de matrícula",
        max_digits=10,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        validators=[positive_amount_validator],
    )
    monthly_fee = models.DecimalField(
        "Mensualidad",
        max_digits=10,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        validators=[positive_amount_validator],
    )
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

    def start_date_display(self):
        return self.start_date.strftime("%d/%m/%Y") if self.start_date else UNASSIGNED_SCHEDULE_NAME

    def _display(self, field_name):
        value = getattr(self, field_name)
        if value is None:
            return UNASSIGNED_SCHEDULE_NAME
        return f"S/ {value:.2f}" if field_name.endswith("_fee") else str(value)

    def capacity_display(self):
        return self._display("capacity")

    def enrollment_fee_display(self):
        return self._display("enrollment_fee")

    def monthly_fee_display(self):
        return self._display("monthly_fee")

    def is_unassigned(self):
        return (
            self.name.upper() == UNASSIGNED_COURSE_NAME
            and self.schedule.upper() == UNASSIGNED_SCHEDULE_NAME
        )

    def clean(self):
        super().clean()
        if not self.is_unassigned():
            required = {
                "start_date": "La fecha de inicio es obligatoria.",
                "capacity": "La capacidad es obligatoria.",
                "enrollment_fee": "El costo de matrícula es obligatorio.",
                "monthly_fee": "La mensualidad es obligatoria.",
            }
            errors = {
                field: message
                for field, message in required.items()
                if getattr(self, field) is None
            }
            if errors:
                raise ValidationError(errors)
        group = (self.group or "").strip()
        if not self.is_unassigned() and not (
            group.isascii() and group.isdigit() and int(group) > 0
        ):
            raise ValidationError({"group": "El grupo debe ser un número entero positivo."})

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        self.schedule = self.schedule.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        detail = f"{self.schedule} · Grupo {self.group}"
        return f"{self.name} ({detail})" if detail else self.name


class Schedule(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    name = models.CharField("Horario", max_length=120)

    class Meta:
        ordering = ["name"]
        verbose_name = "horario"
        verbose_name_plural = "horarios"
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "name"],
                name="unique_schedule_name_per_campus",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Promoter(models.Model):
    name = models.CharField("Nombre del promotor", max_length=120, unique=True)
    campuses = models.ManyToManyField(
        Campus, related_name="promoters", verbose_name="Sedes", blank=True
    )
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "promotor"
        verbose_name_plural = "promotores"

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, verbose_name="Sede")
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="enrollments", verbose_name="Estudiante"
    )
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="enrollments", verbose_name="Curso"
    )
    promoter = models.ManyToManyField(
        Promoter,
        related_name="enrollments",
        verbose_name="Promotores",
        blank=True,
    )
    enrollment_date = models.DateField("Fecha de matrícula", default=timezone.localdate)
    enrollment_fee = models.DecimalField(
        "Costo de matrícula",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[positive_amount_validator],
    )
    monthly_fee = models.DecimalField(
        "Mensualidad",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[positive_amount_validator],
    )
    active = models.BooleanField("Activa", default=True)
    created_at = models.DateTimeField("Creada el", auto_now_add=True)

    class Meta:
        ordering = ["-course__start_date", "student__full_name"]
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.student_id and self.campus_id and self.student.campus_id != self.campus_id:
            raise ValidationError("El estudiante debe pertenecer a la misma sede de la matrícula.")
        if self.course_id and self.campus_id and self.course.campus_id != self.campus_id:
            raise ValidationError("El curso debe pertenecer a la misma sede de la matrícula.")
        if self.student_id and self.course_id and not self.course.is_unassigned():
            duplicates = Enrollment.objects.filter(
                student_id=self.student_id, course_id=self.course_id
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError(
                    {"course": "Este estudiante ya está matriculado en este curso."}
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # La ficha conserva sede y fecha de la matrícula para validar su unicidad.
        Ficha.objects.filter(enrollment_id=self.pk).update(
            campus_id=self.campus_id, date=self.enrollment_date
        )

    @property
    def record_code(self):
        ficha = getattr(self, "ficha", None)
        return ficha.code if ficha else ""

    @property
    def has_record(self):
        return getattr(self, "ficha", None) is not None

    def __str__(self):
        return f"{self.student} — {self.course}"


def validate_ficha_image_size(file):
    if file.size > MAX_FICHA_IMAGE_SIZE:
        raise ValidationError("La imagen de la ficha no puede superar los 10 MB.")


class Ficha(models.Model):
    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.CASCADE, related_name="ficha", verbose_name="Matrícula"
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, editable=False, verbose_name="Sede"
    )
    date = models.DateField("Fecha de matrícula", editable=False)
    code = models.PositiveIntegerField(
        "Código de ficha",
        validators=[MinValueValidator(1, "El código de ficha debe ser un entero positivo.")],
    )
    image = models.ImageField(
        "Imagen de la ficha",
        upload_to="fichas/",
        blank=True,
        validators=[validate_ficha_image_size],
    )
    created_at = models.DateTimeField("Creada el", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizada el", auto_now=True)

    class Meta:
        ordering = ["-date", "code"]
        verbose_name = "ficha"
        verbose_name_plural = "fichas"
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "date", "code"],
                name="unique_ficha_code_per_campus_date",
                violation_error_message=DUPLICATE_FICHA_MESSAGE,
            ),
        ]

    @staticmethod
    def validate_code(code):
        code = str(code if code is not None else "").strip()
        if not (code.isascii() and code.isdigit() and 0 < int(code) <= 2147483647):
            raise ValidationError(
                "El código de ficha es obligatorio y debe ser un entero positivo."
            )

    @staticmethod
    def duplicates(campus_id, date, code, exclude_enrollment_id=None):
        try:
            code = int(str(code).strip())
        except (TypeError, ValueError):
            return Ficha.objects.none()
        same_code = Ficha.objects.filter(campus_id=campus_id, date=date, code=code)
        if exclude_enrollment_id:
            same_code = same_code.exclude(enrollment_id=exclude_enrollment_id)
        return same_code

    def clean(self):
        if self.enrollment_id:
            self.campus_id = self.enrollment.campus_id
            self.date = self.enrollment.enrollment_date
        try:
            self.validate_code(self.code)
        except ValidationError as error:
            raise ValidationError({"code": error.messages})
        if (
            self.campus_id
            and self.date
            and self.duplicates(self.campus_id, self.date, self.code, self.enrollment_id).exists()
        ):
            raise ValidationError({"code": DUPLICATE_FICHA_MESSAGE})

    def __str__(self):
        return f"Ficha {self.code} — {self.enrollment}"
