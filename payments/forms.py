from decimal import Decimal

from django import forms
from django.db.models import DecimalField, Exists, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from core.campus import get_selected_campus
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Enrollment


class PaymentForm(forms.Form):
    receipt_number = forms.CharField(label="N.º de recibo", max_length=40)
    enrollment = forms.ModelChoiceField(queryset=Enrollment.objects.none(), label="Matrícula pendiente")
    amount = forms.DecimalField(label="Importe recibido", min_value=0.01, max_digits=10, decimal_places=2)
    reference = forms.CharField(label="Referencia (opcional)", required=False, max_length=100)
    notes = forms.CharField(label="Observaciones (opcional)", required=False, max_length=250, widget=forms.Textarea(attrs={"rows": 2}))

    def clean_receipt_number(self):
        receipt_number = self.cleaned_data["receipt_number"].strip()
        if Payment.objects.filter(receipt_number=receipt_number).exists():
            raise forms.ValidationError("Este número de recibo ya está registrado.")
        return receipt_number

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        campus = get_selected_campus(request) if request and user else None
        if not campus:
            self.fields["enrollment"].queryset = Enrollment.objects.none()
            return

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
        qs = Enrollment.objects.filter(
            campus=campus,
            active=True,
        ).annotate(has_pending_balance=Exists(pending_installments)).filter(has_pending_balance=True)

        # Buscar por alumno o curso al abrir el formulario; en POST mantenemos
        # todas las matrículas con deuda para validar correctamente la selección.
        query = request.GET.get("q", "").strip() if request and request.method == "GET" else ""
        if query:
            qs = qs.filter(
                Q(student__full_name__icontains=query)
                | Q(course__name__icontains=query)
            )

        self.fields["enrollment"].queryset = qs.select_related("student", "course", "campus").order_by("student__full_name", "course__name")
        self.fields["enrollment"].label_from_instance = self.enrollment_label

    @staticmethod
    def enrollment_label(enrollment):
        pending = sum((item.balance for item in enrollment.installments.filter(active=True)), Decimal("0.00"))
        return f"{enrollment.student.full_name} — {enrollment.course.name} (deuda: S/ {pending:.2f})"
