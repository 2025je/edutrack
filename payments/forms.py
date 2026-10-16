import re
from decimal import Decimal

from django import forms
from django.core.validators import RegexValidator
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from core.campus import get_selected_campus
from payments.models import Installment, Payment, PaymentAllocation, receipt_number_validator
from students.models import Enrollment


def pending_enrollments_for_campus(campus):
    if not campus:
        return Enrollment.objects.none()

    money_field = DecimalField(max_digits=12, decimal_places=2)
    confirmed_allocations = (
        PaymentAllocation.objects.filter(
            installment_id=OuterRef("pk"),
            payment__status=Payment.Status.CONFIRMED,
        )
        .values("installment_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    pending_installments = (
        Installment.objects.filter(enrollment_id=OuterRef("pk"), active=True)
        .annotate(
            paid_total=Coalesce(
                Subquery(confirmed_allocations, output_field=money_field),
                Value(Decimal("0.00"), output_field=money_field),
                output_field=money_field,
            )
        )
        .annotate(pending_balance=F("amount") - F("paid_total"))
        .filter(pending_balance__gt=0)
    )
    pending_totals = (
        pending_installments.order_by()
        .values("enrollment_id")
        .annotate(total=Sum("pending_balance"))
        .values("total")[:1]
    )
    return (
        Enrollment.objects.filter(
            campus=campus,
            active=True,
        )
        .annotate(pending_balance=Subquery(pending_totals, output_field=money_field))
        .filter(pending_balance__gt=0)
    )


class ReceiptNumberWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = [
            forms.TextInput(
                attrs={
                    "maxlength": 1,
                    "pattern": "[A-Za-z]?",
                    "data-uppercase": True,
                    "placeholder": "Letra",
                    "title": "Opcional: una sola letra.",
                    "aria-label": "Letra del recibo (opcional)",
                    "autocomplete": "off",
                    "style": "flex:0 0 5rem;text-transform:uppercase",
                }
            ),
            forms.TextInput(
                attrs={
                    "inputmode": "numeric",
                    "pattern": "[0-9]+",
                    "maxlength": 39,
                    "placeholder": "Número",
                    "title": "Solo números enteros positivos.",
                    "aria-label": "Número del recibo",
                    "autocomplete": "off",
                    "style": "flex:1",
                }
            ),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ["", ""]
        match = re.fullmatch(r"([A-Za-z]?)(\d+)", str(value).strip())
        return list(match.groups()) if match else ["", str(value)]

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        return format_html('<div class="flex gap">{}</div>', mark_safe(html))


class ReceiptNumberField(forms.MultiValueField):
    widget = ReceiptNumberWidget

    def __init__(self, **kwargs):
        fields = (
            forms.CharField(
                required=False,
                max_length=1,
                validators=[
                    RegexValidator(r"^[A-Za-z]$", "Ingrese una sola letra o deje el campo vacío.")
                ],
            ),
            forms.CharField(
                max_length=39,
                validators=[
                    RegexValidator(r"^\d+$", "Ingrese solo números enteros positivos."),
                ],
            ),
        )
        super().__init__(fields=fields, require_all_fields=False, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return ""
        prefix, number = (value.strip() for value in data_list)
        if not number or int(number) <= 0:
            raise forms.ValidationError("El número de recibo debe ser un entero positivo.")
        return f"{prefix.upper()}{number}"


class PaymentForm(forms.Form):
    receipt_number = ReceiptNumberField(label="N.º de recibo")
    enrollment = forms.ModelChoiceField(
        queryset=Enrollment.objects.none(),
        label="Matrícula pendiente",
        widget=forms.RadioSelect,
    )
    amount = forms.DecimalField(
        label="Importe recibido", min_value=0.01, max_digits=10, decimal_places=2
    )
    reference = forms.CharField(label="Referencia (opcional)", required=False, max_length=100)
    notes = forms.CharField(
        label="Observaciones (opcional)",
        required=False,
        max_length=250,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_receipt_number(self):
        receipt_number = self.cleaned_data["receipt_number"].strip().upper()
        receipt_number_validator(receipt_number)
        if (
            self.campus
            and Payment.objects.filter(campus=self.campus, receipt_number=receipt_number).exists()
        ):
            raise forms.ValidationError("Este número de recibo ya está registrado.")
        return receipt_number

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campus = get_selected_campus(request) if request and user else None
        if not self.campus:
            self.fields["enrollment"].queryset = Enrollment.objects.none()
            return

        qs = pending_enrollments_for_campus(self.campus)

        # Buscar por alumno o curso al abrir el formulario; en POST mantenemos
        # todas las matrículas con deuda para validar correctamente la selección.
        query = request.GET.get("q", "").strip() if request and request.method == "GET" else ""
        if query:
            qs = qs.filter(
                Q(student__full_name__unaccent__icontains=query)
                | Q(course__name__unaccent__icontains=query)
            )
        student_id = (
            request.GET.get("student", "").strip() if request and request.method == "GET" else ""
        )
        if student_id:
            try:
                qs = qs.filter(student_id=int(student_id))
            except ValueError:
                qs = qs.none()

        self.fields["enrollment"].queryset = qs.select_related(
            "student", "course", "campus"
        ).order_by("student__full_name", "course__name")
        self.fields["enrollment"].label_from_instance = self.enrollment_label

        enrollment_id = (
            request.GET.get("enrollment", "").strip() if request and request.method == "GET" else ""
        )
        selected_enrollment = None
        if enrollment_id:
            try:
                selected_enrollment = qs.get(pk=int(enrollment_id))
            except (ValueError, Enrollment.DoesNotExist):
                selected_enrollment = None
        elif student_id and qs.count() == 1:
            selected_enrollment = qs.first()
        if selected_enrollment:
            self.initial["enrollment"] = selected_enrollment.pk
            self.initial["amount"] = selected_enrollment.pending_balance

    @staticmethod
    def enrollment_label(enrollment):
        pending = sum(
            (item.balance for item in enrollment.installments.filter(active=True)), Decimal("0.00")
        )
        return (
            f"{enrollment.student.full_name} — {enrollment.course.name} (deuda: S/ {pending:.2f})"
        )


class PaymentUpdateForm(forms.ModelForm):
    receipt_number = ReceiptNumberField(label="N.º de recibo")

    class Meta:
        model = Payment
        fields = ["receipt_number", "enrollment", "amount", "reference", "notes"]

    def clean_receipt_number(self):
        receipt_number = self.cleaned_data["receipt_number"].strip().upper()
        receipt_number_validator(receipt_number)
        if (
            Payment.objects.filter(
                campus=self.instance.campus,
                receipt_number=receipt_number,
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("Este número de recibo ya está registrado.")
        return receipt_number

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        campus = get_selected_campus(request) if request and user else None
        if campus:
            self.fields["enrollment"].queryset = (
                Enrollment.objects.filter(campus=campus)
                .filter(Q(active=True) | Q(pk=self.instance.enrollment_id))
                .select_related("student", "course")
            )
        else:
            self.fields["enrollment"].queryset = Enrollment.objects.none()
