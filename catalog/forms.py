from django import forms
from django.core.exceptions import ValidationError

from students.models import Course, Promoter, Schedule


class CourseForm(forms.ModelForm):
    schedule = forms.ModelChoiceField(
        label="Horario",
        queryset=Schedule.objects.order_by("name"),
        empty_label=None,
    )

    class Meta:
        model = Course
        fields = [
            "name",
            "schedule",
            "group",
            "capacity",
            "start_date",
            "enrollment_fee",
            "monthly_fee",
        ]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, campus=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campus = campus

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_schedule(self):
        return self.cleaned_data["schedule"].name

    def clean(self):
        cleaned = super().clean()
        if self.campus and all(cleaned.get(key) for key in ("name", "schedule", "group")):
            if Course.objects.filter(
                campus=self.campus,
                name__iexact=cleaned["name"],
                schedule=cleaned["schedule"],
                group__iexact=cleaned["group"],
            ).exists():
                raise ValidationError(
                    "Ya existe un curso con ese nombre, horario y grupo en esta sede."
                )
        return cleaned


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ["name"]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Schedule.objects.filter(name__iexact=name).exists():
            raise ValidationError("Ya existe un horario con ese nombre.")
        return name


class PromoterForm(forms.ModelForm):
    class Meta:
        model = Promoter
        fields = ["name"]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Promoter.objects.filter(name__iexact=name).exists():
            raise ValidationError("Ya existe un promotor con ese nombre.")
        return name
