from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import Student, Enrollment, Course, Promoter
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
            option["attrs"]["data-registration-fee"] = str(registration)
            option["attrs"]["data-monthly-fee"] = str(monthly)
            option["attrs"]["data-capacity"] = str(capacity)
            option["attrs"]["data-enrolled-count"] = str(enrolled_count)
        return option


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["full_name", "document_number", "phone", "active"]
        widgets = {
            "full_name": forms.TextInput(attrs={"autofocus": True}),
            "phone": forms.TextInput(attrs={"placeholder": "987654321, 912345678"}),
        }

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        # La sede proviene de la sesión, nunca del formulario enviado por el navegador.
        self.selected_campus = get_selected_campus(request) if request and user else None

    def clean_phone(self):
        phone_numbers = self.cleaned_data["phone"].split(",")
        return ", ".join(number.strip() for number in phone_numbers if number.strip())


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["course", "student", "record_code", "promoter", "enrollment_fee", "monthly_fee", "active"]

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
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
            self.fields["course"].queryset = course_queryset
        else:
            self.fields["course"].queryset = Course.objects.none()

        # No mostrar alumnos hasta que se elija un curso. Si el formulario
        # se envía o vuelve con errores, validar solo alumnos elegibles para ese curso.
        selected_course_id = (self.data.get("course") if self.is_bound else self.initial.get("course"))
        selected_course = None
        if selected and selected_course_id:
            try:
                selected_course = self.fields["course"].queryset.get(pk=int(selected_course_id))
            except (ValueError, TypeError, Course.DoesNotExist):
                selected_course = None

        if selected_course:
            already_enrolled_ids = Enrollment.objects.filter(
                course=selected_course
            )
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
        if selected:
            promoters = Promoter.objects.filter(models.Q(campuses=selected) | models.Q(campuses__isnull=True))
            if self.instance.pk and self.instance.promoter_id:
                promoters = promoters.filter(
                    models.Q(active=True) | models.Q(pk=self.instance.promoter_id)
                )
            else:
                promoters = promoters.filter(active=True)
            self.fields["promoter"].queryset = promoters.distinct()
        else:
            self.fields["promoter"].queryset = Promoter.objects.none()

        courses = list(self.fields["course"].queryset)
        course_info = {}
        for course in courses:
            enrolled_count = Enrollment.objects.filter(course=course, active=True).count()
            course_info[str(course.pk)] = (
                course.enrollment_fee, course.monthly_fee, course.capacity, enrolled_count
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
        if not campus:
            raise ValidationError("Primero debes seleccionar una sede.")
        if student and course:
            if student.campus_id != campus.pk or course.campus_id != campus.pk:
                raise ValidationError("El estudiante y el curso deben pertenecer a la sede seleccionada.")
            duplicate = Enrollment.objects.filter(student=student, course=course)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("course", "Este estudiante ya está matriculado en este curso.")
        return cleaned
