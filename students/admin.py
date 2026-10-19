from django.contrib import admin
from django import forms

from .models import (
    Course,
    Enrollment,
    Ficha,
    Promoter,
    Schedule,
    Student,
)


class StudentAdminForm(forms.ModelForm):
    last_name = forms.CharField(label="Apellidos", max_length=120)
    first_name = forms.CharField(label="Nombres", max_length=120)

    class Meta:
        model = Student
        fields = ["campus", "last_name", "first_name", "document_number", "phone", "active"]

    def clean(self):
        cleaned_data = super().clean()
        last_name = cleaned_data.get("last_name", "").strip().upper()
        first_name = cleaned_data.get("first_name", "").strip().upper()
        cleaned_data["last_name"] = last_name
        cleaned_data["first_name"] = first_name
        full_name = " ".join(part.strip() for part in (last_name, first_name) if part.strip())
        if full_name:
            duplicate = Student.objects.filter(
                campus=cleaned_data.get("campus"), full_name__iexact=full_name
            )
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
        if commit:
            student.save()
            self.save_m2m()
        return student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentAdminForm
    list_display = ("full_name", "campus", "phone", "active")
    list_filter = ("campus", "active")
    search_fields = ("full_name", "document_number")


class CourseAdminForm(forms.ModelForm):
    schedule = forms.ModelChoiceField(
        label="Horario",
        queryset=Schedule.objects.order_by("name"),
        empty_label=None,
    )

    class Meta:
        model = Course
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campus_id = (
            self.data.get("campus")
            or self.initial.get("campus")
            or getattr(self.instance, "campus_id", None)
        )
        if campus_id:
            self.fields["schedule"].queryset = self.fields["schedule"].queryset.filter(
                campus_id=campus_id
            )
        else:
            self.fields["schedule"].queryset = Schedule.objects.none()
        if self.instance.pk and campus_id:
            self.initial["schedule"] = Schedule.objects.filter(
                campus_id=campus_id, name=self.instance.schedule
            ).first()

    def clean_schedule(self):
        schedule = self.cleaned_data["schedule"]
        campus = self.cleaned_data.get("campus")
        if campus and schedule.campus_id != campus.pk:
            raise forms.ValidationError("El horario debe pertenecer a la misma sede del curso.")
        return schedule.name


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = (
        "name",
        "campus",
        "start_date",
        "schedule",
        "group",
        "capacity",
        "enrollment_fee",
        "monthly_fee",
        "active",
    )
    list_filter = ("campus", "active")
    search_fields = ("name", "schedule", "group")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "campus")
    list_filter = ("campus",)
    search_fields = ("name",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "record_code", "promoter_names", "campus", "active")
    list_filter = ("campus", "active")
    search_fields = ("student__full_name", "course__name", "ficha__code", "promoter__name")

    @admin.display(description="Promotores")
    def promoter_names(self, enrollment):
        return ", ".join(enrollment.promoter.values_list("name", flat=True)) or "—"


@admin.register(Ficha)
class FichaAdmin(admin.ModelAdmin):
    list_display = ("code", "enrollment", "date", "campus")
    list_filter = ("campus",)
    search_fields = ("code", "enrollment__student__full_name")
    raw_id_fields = ("enrollment",)
    readonly_fields = ("campus", "date")


@admin.register(Promoter)
class PromoterAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active", "campuses")
    search_fields = ("name",)
    filter_horizontal = ("campuses",)
