from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import (
    DEFAULT_PROMOTER_NAMES,
    UNASSIGNED_COURSE_NAME,
    UNASSIGNED_SCHEDULE_NAME,
    Student,
    Enrollment,
    Course,
    Promoter,
    phone_validator,
)
from core.campus import get_selected_campus


class CourseSelectWidget(forms.Select):
    def __init__(self, course_prices=None, *args, **kwargs):
        self.course_prices = course_prices or {}
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
            duplicate = Student.objects.filter(full_name__iexact=full_name)
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
    class Meta:
        model = Enrollment
        fields = [
            "course",
            "student",
            "has_record",
            "record_code",
            "promoter",
            "enrollment_date",
            "enrollment_fee",
            "monthly_fee",
            "active",
        ]
        widgets = {
            "promoter": forms.CheckboxSelectMultiple,
            "record_code": forms.TextInput(
                attrs={
                    "inputmode": "numeric",
                    "pattern": r"\d*",
                }
            ),
            "enrollment_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, user=None, request=None, locked_student=None, **kwargs):
        super().__init__(*args, **kwargs)
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
            self.fields["course"].queryset = course_queryset
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
            choices=self.fields["course"].choices,
        )
        # self.fields["course"].widget = CourseSelectWidget(course_info)
        if selected_course and not self.instance.pk:
            self.fields["enrollment_fee"].initial = selected_course.enrollment_fee
            self.fields["monthly_fee"].initial = selected_course.monthly_fee

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        course = cleaned.get("course")
        campus = self.selected_campus
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
        return cleaned
