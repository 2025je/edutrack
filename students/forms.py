from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.core.files.uploadedfile import UploadedFile
from django.db import models, transaction
from .models import (
    DEFAULT_PROMOTER_NAMES,
    DUPLICATE_FICHA_MESSAGE,
    Ficha,
    record_code_validator,
    validate_ficha_image_size,
    UNASSIGNED_COURSE_NAME,
    UNASSIGNED_SCHEDULE_NAME,
    Student,
    Enrollment,
    Course,
    Promoter,
    phone_validator,
)
from core.campus import get_selected_campus
from .images import DEFAULT_QUALITY, QUALITY_CHOICES, to_jpeg


class CourseSelectWidget(forms.Select):
    def __init__(self, course_prices=None, unassigned_ids=None, *args, **kwargs):
        self.course_prices = course_prices or {}
        self.unassigned_ids = unassigned_ids or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        key = str(value)
        if key in self.course_prices:
            registration, monthly, capacity, enrolled_count = self.course_prices[key]
            option["attrs"]["data-registration-fee"] = (
                "" if registration is None else str(registration)
            )
            option["attrs"]["data-monthly-fee"] = "" if monthly is None else str(monthly)
            option["attrs"]["data-capacity"] = "" if capacity is None else str(capacity)
            option["attrs"]["data-enrolled-count"] = str(enrolled_count)
            option["attrs"]["data-unassigned"] = "true" if self.unassigned_ids.get(key) else "false"
        return option


class PhoneListWidget(forms.TextInput):
    def value_from_datadict(self, data, files, name):
        if hasattr(data, "getlist"):
            raw_values = data.getlist(name)
        else:
            raw_value = data.get(name, "")
            raw_values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
        values = [value.strip() for value in raw_values]
        return ", ".join(values)


class StudentForm(forms.ModelForm):
    last_name = forms.CharField(
        label="Apellidos",
        max_length=120,
        widget=forms.TextInput(
            attrs={"autofocus": True, "data-uppercase": True, "style": "text-transform:uppercase"}
        ),
    )
    first_name = forms.CharField(
        label="Nombres",
        max_length=120,
        widget=forms.TextInput(attrs={"data-uppercase": True, "style": "text-transform:uppercase"}),
    )
    phone_numbers = forms.CharField(
        label="Teléfonos",
        required=True,
        widget=PhoneListWidget(
            attrs={
                "placeholder": "987654321",
                "inputmode": "numeric",
                "pattern": "9[0-9]{8}",
                "maxlength": 9,
                "required": True,
            }
        ),
    )

    class Meta:
        model = Student
        fields = ["last_name", "first_name", "document_number", "active"]
        # Los teléfonos son un campo declarado; se ordenan junto a los datos de contacto.

    field_order = ["last_name", "first_name", "document_number", "phone_numbers", "active"]

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        # La sede proviene de la sesión, nunca del formulario enviado por el navegador.
        self.selected_campus = get_selected_campus(request) if request and user else None
        if self.instance and self.instance.phone:
            self.initial["phone_numbers"] = self.instance.phone

    def clean_phone_numbers(self):
        phone_numbers = [
            number.strip() for number in self.cleaned_data.get("phone_numbers", "").split(",")
        ]
        if not phone_numbers or any(not number for number in phone_numbers):
            raise ValidationError("Ingrese al menos un teléfono y complete todos los campos.")
        for phone in phone_numbers:
            try:
                phone_validator(phone)
            except ValidationError:
                raise ValidationError(
                    f"El teléfono {phone} no es válido. Use 9 dígitos y empiece con 9."
                )
        return ", ".join(phone_numbers)

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip().upper()

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        full_name = " ".join(
            part.strip()
            for part in (
                cleaned_data.get("last_name", ""),
                cleaned_data.get("first_name", ""),
            )
            if part.strip()
        )
        full_name = full_name.upper()
        if full_name:
            campus = self.selected_campus
            if not campus and self.instance.campus_id:
                campus = self.instance.campus
            if campus:
                duplicate = Student.objects.filter(campus=campus, full_name__iexact=full_name)
                if self.instance.pk:
                    duplicate = duplicate.exclude(pk=self.instance.pk)
                if duplicate.exists():
                    self.add_error(
                        "last_name", "Ya existe un estudiante con estos apellidos y nombres."
                    )
        cleaned_data["full_name"] = full_name
        return cleaned_data

    def save(self, commit=True):
        student = super().save(commit=False)
        student.full_name = self.cleaned_data["full_name"]
        student.phone = self.cleaned_data["phone_numbers"]
        if commit:
            student.save()
            self.save_m2m()
        return student


class EnrollmentForm(forms.ModelForm):
    record_code = forms.CharField(
        label="Código de ficha",
        max_length=50,
        required=False,
        validators=[record_code_validator],
        widget=forms.TextInput(attrs={"inputmode": "numeric", "pattern": r"[1-9]\d*"}),
    )
    record_image = forms.ImageField(
        label="Imagen de la ficha (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
        validators=[validate_ficha_image_size],
    )
    record_image_quality = forms.ChoiceField(
        label="Compresión de la imagen",
        choices=QUALITY_CHOICES,
        initial=DEFAULT_QUALITY,
        required=False,
        widget=forms.RadioSelect,
        help_text="La imagen se guardará como JPEG con esta calidad.",
    )

    class Meta:
        model = Enrollment
        fields = [
            "course",
            "student",
            "enrollment_date",
            "promoter",
            "record_code",
            "record_image",
            "record_image_quality",
            "enrollment_fee",
            "monthly_fee",
            "active",
        ]
        widgets = {
            "promoter": forms.CheckboxSelectMultiple,
            "enrollment_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, user=None, request=None, locked_student=None, **kwargs):
        super().__init__(*args, **kwargs)
        ficha = getattr(self.instance, "ficha", None) if self.instance.pk else None
        if ficha:
            self.initial["record_code"] = ficha.code
            self.initial["record_image"] = ficha.image
        self.locked_student = locked_student
        # La sede se obtiene de la sesión del usuario y no se muestra como campo.
        self.selected_campus = get_selected_campus(request) if request and user else None
        selected = self.selected_campus
        if selected:
            course_queryset = Course.objects.filter(campus=selected)
            if self.instance.pk:
                course_queryset = course_queryset.filter(
                    models.Q(active=True) | models.Q(pk=self.instance.course_id)
                )
            else:
                course_queryset = course_queryset.filter(active=True)
            if locked_student:
                course_queryset = course_queryset.exclude(
                    pk__in=Enrollment.objects.filter(student=locked_student)
                    .exclude(
                        course__name=UNASSIGNED_COURSE_NAME,
                        course__schedule=UNASSIGNED_SCHEDULE_NAME,
                    )
                    .values_list("course_id", flat=True)
                )
            # POR ASIGNAR siempre aparece primero y es el valor por defecto al crear.
            course_queryset = course_queryset.annotate(
                is_not_unassigned=models.Case(
                    models.When(
                        name=UNASSIGNED_COURSE_NAME,
                        schedule=UNASSIGNED_SCHEDULE_NAME,
                        then=0,
                    ),
                    default=1,
                    output_field=models.IntegerField(),
                )
            ).order_by("is_not_unassigned", "name", "schedule", "group")
            self.fields["course"].queryset = course_queryset
            if self.instance.pk and user and not user.has_perm("core.change_enrollment_course"):
                self.fields["course"].queryset = course_queryset.filter(pk=self.instance.course_id)
                self.fields["course"].disabled = True
            if not self.instance.pk:
                default_course = course_queryset.filter(is_not_unassigned=0).first()
                if default_course:
                    self.fields["course"].empty_label = None
                    if not self.is_bound and not self.initial.get("course"):
                        self.initial["course"] = default_course.pk
        else:
            self.fields["course"].queryset = Course.objects.none()

        # No mostrar alumnos hasta que se elija un curso. Si el formulario
        # se envía o vuelve con errores, validar solo alumnos elegibles para ese curso.
        selected_course_id = (
            self.data.get("course") if self.is_bound else self.initial.get("course")
        )
        selected_course = None
        if selected and selected_course_id:
            try:
                selected_course = self.fields["course"].queryset.get(pk=int(selected_course_id))
            except (ValueError, TypeError, Course.DoesNotExist):
                selected_course = None

        if selected_course:
            already_enrolled_ids = Enrollment.objects.filter(course=selected_course)
            if selected_course.is_unassigned():
                already_enrolled_ids = already_enrolled_ids.none()
            if self.instance.pk:
                already_enrolled_ids = already_enrolled_ids.exclude(pk=self.instance.pk)
            already_enrolled_ids = already_enrolled_ids.values_list("student_id", flat=True)
            eligible_students = Student.objects.filter(campus=selected, active=True)
            if self.instance.pk and self.instance.student_id:
                eligible_students = Student.objects.filter(campus=selected).filter(
                    models.Q(active=True) | models.Q(pk=self.instance.student_id)
                )
            self.fields["student"].queryset = eligible_students.exclude(pk__in=already_enrolled_ids)
        else:
            self.fields["student"].queryset = Student.objects.none()
        if locked_student:
            self.fields["student"].queryset = Student.objects.filter(pk=locked_student.pk)
            self.fields["student"].widget = forms.HiddenInput()
        if selected:
            promoters = Promoter.objects.filter(
                models.Q(campuses=selected) | models.Q(campuses__isnull=True)
            )
            if self.instance.pk:
                selected_promoter_ids = self.instance.promoter.values_list("pk", flat=True)
                promoters = promoters.filter(
                    models.Q(active=True) | models.Q(pk__in=selected_promoter_ids)
                )
            else:
                promoters = promoters.filter(active=True)
            promoters = promoters.distinct().annotate(
                is_default=models.Case(
                    models.When(name__in=DEFAULT_PROMOTER_NAMES, then=1),
                    default=0,
                    output_field=models.IntegerField(),
                )
            )
            self.fields["promoter"].queryset = promoters.order_by("is_default", "name")
        else:
            self.fields["promoter"].queryset = Promoter.objects.none()

        courses = list(self.fields["course"].queryset)
        course_info = {}
        for course in courses:
            enrolled_count = Enrollment.objects.filter(course=course, active=True).count()
            course_info[str(course.pk)] = (
                course.enrollment_fee,
                course.monthly_fee,
                course.capacity,
                enrolled_count,
            )
        self.fields["course"].widget = CourseSelectWidget(
            course_prices=course_info,
            unassigned_ids={str(c.pk): c.is_unassigned() for c in courses},
            choices=self.fields["course"].choices,
        )
        # self.fields["course"].widget = CourseSelectWidget(course_info)
        if selected_course and not self.instance.pk:
            self.fields["enrollment_fee"].initial = selected_course.enrollment_fee
            self.fields["monthly_fee"].initial = selected_course.monthly_fee

        # Con POR ASIGNAR los costos son siempre 0 (se validan manualmente en el resto de cursos).
        self.fee_fields = ("enrollment_fee", "monthly_fee")
        for name in self.fee_fields:
            field = self.fields[name]
            field.validators = [v for v in field.validators if not isinstance(v, MinValueValidator)]
        self.selected_is_unassigned = bool(selected_course and selected_course.is_unassigned())
        if self.selected_is_unassigned:
            if self.is_bound:
                self.data = self.data.copy()
                for name in self.fee_fields:
                    self.data[self.add_prefix(name)] = "0"
            else:
                for name in self.fee_fields:
                    self.initial[name] = Decimal("0")
                    self.fields[name].initial = Decimal("0")
            for name in self.fee_fields:
                self.fields[name].widget.attrs["readonly"] = True

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.update(self.fee_fields)
        return exclude

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        course = cleaned.get("course")
        campus = self.selected_campus
        if course and course.is_unassigned():
            for name in self.fee_fields:
                cleaned[name] = Decimal("0")
        else:
            for name in self.fee_fields:
                value = cleaned.get(name)
                if value is not None and value < Decimal("0.01"):
                    self.add_error(name, "El valor debe ser mayor a 0.")
        promoters = cleaned.get("promoter")
        if promoters and len(promoters) > 1:
            if any(p.name in DEFAULT_PROMOTER_NAMES for p in promoters):
                self.add_error(
                    "promoter",
                    "PARTICULAR y NN no se pueden combinar con otros promotores.",
                )
        if not campus:
            raise ValidationError("Primero debes seleccionar una sede.")
        if student and course:
            if student.campus_id != campus.pk or course.campus_id != campus.pk:
                raise ValidationError(
                    "El estudiante y el curso deben pertenecer a la sede seleccionada."
                )
            duplicate = Enrollment.objects.filter(student=student, course=course)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists() and not course.is_unassigned():
                self.add_error("course", "Este estudiante ya está matriculado en este curso.")
        record_code = (cleaned.get("record_code") or "").strip()
        record_image = cleaned.get("record_image")
        enrollment_date = cleaned.get("enrollment_date")
        if record_code:
            try:
                Ficha.validate_code(record_code)
            except ValidationError as error:
                if "record_code" not in self.errors:
                    self.add_error("record_code", error)
            else:
                if (
                    enrollment_date
                    and Ficha.duplicates(
                        campus.pk, enrollment_date, record_code, self.instance.pk
                    ).exists()
                ):
                    self.add_error("record_code", DUPLICATE_FICHA_MESSAGE)
        elif isinstance(record_image, UploadedFile):
            self.add_error(
                "record_image",
                "Ingresa el código de ficha para poder subir la imagen.",
            )
        return cleaned

    def save(self, commit=True):
        enrollment = super().save(commit=commit)
        if commit:
            self._save_ficha(enrollment)
        else:
            save_m2m = self.save_m2m

            def save_m2m_and_ficha():
                save_m2m()
                self._save_ficha(enrollment)

            self.save_m2m = save_m2m_and_ficha
        return enrollment

    def _save_ficha(self, enrollment):
        ficha = getattr(enrollment, "ficha", None)
        old_image = ficha.image.name if ficha else ""
        if not (self.cleaned_data.get("record_code") or "").strip():
            if ficha:
                ficha.delete()
                self._delete_file_on_commit(ficha, old_image)
            return
        ficha = ficha or Ficha(enrollment=enrollment)
        ficha.campus_id = enrollment.campus_id
        ficha.date = enrollment.enrollment_date
        ficha.code = int(self.cleaned_data["record_code"].strip())
        record_image = self.cleaned_data.get("record_image")
        if isinstance(record_image, UploadedFile):
            ficha.image = to_jpeg(
                record_image, self.cleaned_data.get("record_image_quality") or DEFAULT_QUALITY
            )
        elif record_image is False:
            ficha.image = ""
        ficha.save()
        if old_image and old_image != ficha.image.name:
            self._delete_file_on_commit(ficha, old_image)

    @staticmethod
    def _delete_file_on_commit(ficha, name):
        # El archivo anterior se borra solo si la transacción se confirma.
        if name:
            transaction.on_commit(lambda: ficha.image.storage.delete(name))
