import re
from datetime import date
from decimal import Decimal

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import RegexValidator
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from core.campus import get_selected_campus
from payments.models import Installment, Payment, PaymentAllocation, receipt_number_validator
from students.models import Enrollment, validate_ficha_image_size
from students.images import DEFAULT_QUALITY, QUALITY_CHOICES, to_jpeg


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


def filter_pending_enrollments(qs, get):
    """Aplica los filtros de la pantalla de búsqueda de matrículas con deuda."""

    def param(name):
        return str(get.get(name, "")).strip()

    def number(name, kind=int):
        try:
            return kind(param(name))
        except (ValueError, ArithmeticError):
            return None

    query = param("q")
    if query:
        qs = qs.filter(
            Q(student__full_name__unaccent__icontains=query)
            | Q(course__name__unaccent__icontains=query)
        )
    if param("dni"):
        qs = qs.filter(student__document_number__icontains=param("dni"))
    if param("course"):
        course_id = number("course")
        qs = qs.filter(course_id=course_id) if course_id else qs.none()
    if param("schedule"):
        qs = qs.filter(course__schedule__icontains=param("schedule"))
    if param("group"):
        qs = qs.filter(course__group__iexact=param("group"))
    if param("promoter"):
        promoter_id = number("promoter")
        qs = qs.filter(promoter__id=promoter_id) if promoter_id else qs.none()
    if param("ficha"):
        ficha_code = number("ficha")
        qs = qs.filter(ficha__code=ficha_code) if ficha_code else qs.none()
    if param("student"):
        student_id = number("student")
        qs = qs.filter(student_id=student_id) if student_id else qs.none()
    for name, lookup in (("date_from", "gte"), ("date_to", "lte")):
        if param(name):
            try:
                qs = qs.filter(**{f"enrollment_date__{lookup}": date.fromisoformat(param(name))})
            except ValueError:
                qs = qs.none()
    for name, lookup in (("debt_min", "gte"), ("debt_max", "lte")):
        if param(name):
            amount = number(name, Decimal)
            qs = (
                qs.filter(**{f"pending_balance__{lookup}": amount})
                if amount is not None
                else qs.none()
            )
    return qs.distinct()


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


class VoucherFieldsMixin(forms.Form):
    voucher = forms.ImageField(
        label="Foto del voucher (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
        validators=[validate_ficha_image_size],
    )
    voucher_quality = forms.ChoiceField(
        label="Compresión de la imagen",
        choices=QUALITY_CHOICES,
        initial=DEFAULT_QUALITY,
        required=False,
        widget=forms.RadioSelect,
        help_text="La imagen se guardará como JPEG con esta calidad.",
    )

    def voucher_file(self):
        """Devuelve la imagen convertida a JPEG, False si se pidió quitarla, o None si no cambió."""
        voucher = self.cleaned_data.get("voucher")
        if isinstance(voucher, UploadedFile):
            return to_jpeg(voucher, self.cleaned_data.get("voucher_quality") or DEFAULT_QUALITY)
        return False if voucher is False else None


class PaymentForm(VoucherFieldsMixin, forms.Form):
    field_order = [
        "enrollment",
        "receipt_number",
        "amount",
        "reference",
        "notes",
        "voucher",
        "voucher_quality",
    ]
    receipt_number = ReceiptNumberField(label="N.º de recibo")
    enrollment = forms.ModelChoiceField(
        queryset=Enrollment.objects.none(),
        label="Matrícula pendiente",
        widget=forms.HiddenInput,
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

    def __init__(self, *args, user=None, request=None, enrollment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.campus = get_selected_campus(request) if request and user else None
        self.fields["enrollment"].queryset = (
            pending_enrollments_for_campus(self.campus).select_related("student", "course")
            if self.campus
            else Enrollment.objects.none()
        )
        if enrollment is not None:
            self.initial["enrollment"] = enrollment.pk
            self.initial["amount"] = enrollment.pending_balance


class PaymentUpdateForm(VoucherFieldsMixin, forms.ModelForm):
    field_order = [
        "enrollment",
        "receipt_number",
        "amount",
        "reference",
        "notes",
        "voucher",
        "voucher_quality",
    ]
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
        if self.instance.pk and self.instance.voucher:
            self.initial["voucher"] = self.instance.voucher
        campus = get_selected_campus(request) if request and user else None
        if campus:
            self.fields["enrollment"].queryset = (
                Enrollment.objects.filter(campus=campus)
                .filter(Q(active=True) | Q(pk=self.instance.enrollment_id))
                .select_related("student", "course")
            )
        else:
            self.fields["enrollment"].queryset = Enrollment.objects.none()
