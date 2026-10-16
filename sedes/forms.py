from django import forms

from core.models import Campus, User


class CampusForm(forms.ModelForm):
    class Meta:
        model = Campus
        fields = ["name", "address", "logo", "active"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Campus.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una sede con ese nombre.")
        return name


class UserCampusesForm(forms.ModelForm):
    campuses = forms.ModelMultipleChoiceField(
        label="Sedes asignadas",
        queryset=Campus.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ["campuses"]
