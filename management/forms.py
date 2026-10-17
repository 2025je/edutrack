import os

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.models import Campus, CampusFlyer, User
from students.models import UNASSIGNED_SCHEDULE_NAME, Course, Promoter, Schedule

PERMISSION_FIELDS = [
    "can_manage_students",
    "can_register_payments",
    "can_manage_promoters",
    "can_manage_calls",
    "can_edit_call_notes",
    "can_assign_calls",
    "can_manage_campuses",
    "can_manage_users",
]


class CampusForm(forms.ModelForm):
    class Meta:
        model = Campus
        fields = ["name", "address", "logo", "active"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Campus.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una sede con ese nombre.")
        return name


class CampusFlyerForm(forms.ModelForm):
    class Meta:
        model = CampusFlyer
        fields = ["title", "file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={
                    "accept": "application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp"
                }
            )
        }

    def __init__(self, *args, optional=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Opcional: el navegador no exige los campos; la vista valida solo si se llenó alguno.
        self.use_required_attribute = not optional
        self.fields["title"].required = False

    def clean(self):
        cleaned = super().clean()
        title = (cleaned.get("title") or "").strip()
        file = cleaned.get("file")
        if file and not title:
            title = os.path.splitext(os.path.basename(file.name))[0][:120]
        if title and not file and "file" not in self.errors:
            self.add_error("file", "Seleccione el archivo del volante.")
        cleaned["title"] = title
        return cleaned


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    campuses = forms.ModelMultipleChoiceField(
        label="Sedes que puede manejar",
        queryset=Campus.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ["username", *PERMISSION_FIELDS]
        labels = {"username": "Nombre de usuario"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.permission_fields = [self[name] for name in PERMISSION_FIELDS]

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                user = self.instance if self.instance.pk else User()
                user.username = cleaned.get("username", user.username)
                try:
                    validate_password(password1, user)
                except ValidationError as error:
                    self.add_error("password1", error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            user.campuses.set(self.cleaned_data["campuses"])
        return user


class UserUpdateForm(UserCreateForm):
    class Meta(UserCreateForm.Meta):
        fields = ["username", "is_active", *PERMISSION_FIELDS]
        labels = {"username": "Nombre de usuario", "is_active": "Usuario activo"}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        for name in ("password1", "password2"):
            self.fields[name].required = False
        self.fields["password1"].label = "Nueva contraseña"
        self.fields["password2"].label = "Confirmar nueva contraseña"
        if self.instance.pk:
            self.fields["campuses"].initial = self.instance.campuses.all()

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if not is_active and self.editor and self.editor.pk == self.instance.pk:
            raise ValidationError("No puedes desactivar tu propio usuario.")
        return is_active


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
            "start_date",
            "capacity",
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
        self.fields["schedule"].queryset = (
            Schedule.objects.filter(campus=campus)
            .exclude(name=UNASSIGNED_SCHEDULE_NAME)
            .order_by("name")
            if campus
            else Schedule.objects.none()
        )

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

    def __init__(self, *args, campus=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campus = campus

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split()).upper()
        if self.campus and Schedule.objects.filter(campus=self.campus, name__iexact=name).exists():
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
