from django.contrib import admin
from django import forms

from .models import Student, Course, Enrollment, Promoter, Schedule


class StudentAdminForm(forms.ModelForm):
    last_name = forms.CharField(label="Apellidos", max_length=120)
    first_name = forms.CharField(label="Nombres", max_length=120)

    class Meta:
        model = Student
        fields = ["campus", "last_name", "first_name", "document_number", "phone", "active"]

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
        if full_name:
            duplicate = Student.objects.filter(full_name=full_name)
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
        if self.instance.pk:
            self.initial["schedule"] = Schedule.objects.filter(
                name=self.instance.schedule
            ).first()

    def clean_schedule(self):
        return self.cleaned_data["schedule"].name


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = ("name", "campus", "start_date", "schedule", "group", "capacity", "enrollment_fee", "monthly_fee", "active")
    list_filter = ("campus", "active")
    search_fields = ("name", "schedule", "group")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    search_fields = ("name",)

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "record_code", "promoter_names", "campus", "active")
    list_filter = ("campus", "active")
    search_fields = ("student__full_name", "course__name", "record_code", "promoter__name")

    @admin.display(description="Promotores")
    def promoter_names(self, enrollment):
        return ", ".join(enrollment.promoter.values_list("name", flat=True)) or "—"


@admin.register(Promoter)
class PromoterAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active", "campuses")
    search_fields = ("name",)
    filter_horizontal = ("campuses",)
