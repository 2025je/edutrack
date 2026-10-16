from django import forms
from django.core.exceptions import ValidationError

from students.models import UNASSIGNED_SCHEDULE_NAME, Course, Promoter, Schedule


class CourseForm(forms.ModelForm):
    schedule = forms.ModelChoiceField(
        label="Horario",
        queryset=Schedule.objects.exclude(name=UNASSIGNED_SCHEDULE_NAME).order_by("name"),
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
        widgets = {
            "name": forms.TextInput(
                attrs={"data-uppercase": True, "style": "text-transform:uppercase"}
            ),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "group": forms.NumberInput(attrs={"min": 1, "step": 1}),
        }

    def __init__(self, *args, campus=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campus = campus

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split()).upper()

    def clean_group(self):
        return (
            str(int(self.cleaned_data["group"]))
            if self.cleaned_data["group"].strip().isdigit()
            else self.cleaned_data["group"]
        )

    def clean_schedule(self):
        return self.cleaned_data["schedule"].name.upper()

    def clean(self):
        cleaned = super().clean()
        if self.campus and all(cleaned.get(key) for key in ("name", "schedule", "group")):
            if Course.objects.filter(
                campus=self.campus,
                name__iexact=cleaned["name"],
                schedule__iexact=cleaned["schedule"],
                group__iexact=cleaned["group"],
            ).exists():
                raise ValidationError(
                    "Ya existe un curso con ese nombre, horario y grupo en esta sede."
                )
        return cleaned


class CourseStartDateForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["start_date", "capacity", "enrollment_fee", "monthly_fee"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"data-uppercase": True, "style": "text-transform:uppercase"}
            ),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split()).upper()
        if Schedule.objects.filter(name__iexact=name).exists():
            raise ValidationError("Ya existe un horario con ese nombre.")
        return name


class PromoterForm(forms.ModelForm):
    class Meta:
        model = Promoter
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"data-uppercase": True, "style": "text-transform:uppercase"}
            ),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split()).upper()
        if Promoter.objects.filter(name__iexact=name).exists():
            raise ValidationError("Ya existe un promotor con ese nombre.")
        return name
