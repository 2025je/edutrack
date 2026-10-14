from decimal import Decimal
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, DetailView, UpdateView, DeleteView
from core.campus import SelectedCampusRequiredMixin, FeaturePermissionMixin, get_selected_campus
from students.models import Enrollment
from .forms import PaymentForm, PaymentUpdateForm
from .models import Payment, PaymentAllocation, Installment


class SelectedCampusViewMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    permission_field = "can_register_payments"


class PaymentListView(SelectedCampusViewMixin, ListView):
    model = Payment
    template_name = "payments/payment_list.html"
    context_object_name = "payments"
    paginate_by = 30

    def get_queryset(self):
        qs = Payment.objects.filter(campus=get_selected_campus(self.request)).select_related("campus", "enrollment__student", "enrollment__course", "cashier")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(receipt_number__icontains=q) | Q(enrollment__student__full_name__icontains=q))
        return qs


class PaymentCreateView(SelectedCampusViewMixin, FormView):
    template_name = "payments/payment_form.html"
    form_class = PaymentForm
    success_url = reverse_lazy("payment-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        enrollment = form.cleaned_data["enrollment"]
        campus = get_selected_campus(self.request)
        user = self.request.user
        if enrollment.campus_id != campus.pk or not user.can_access_campus(campus):
            return HttpResponseForbidden("No tiene permiso para cobrar en esta sede.")
        amount = form.cleaned_data["amount"]
        try:
            with transaction.atomic():
                # Serializa pagos de una misma matrícula para validar el primer pago sin carreras concurrentes.
                from students.models import Enrollment
                enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk, campus=campus)
                has_confirmed_payment = Payment.objects.filter(enrollment=enrollment, status=Payment.Status.CONFIRMED).exists()
                if not has_confirmed_payment and amount < enrollment.enrollment_fee:
                    form.add_error("amount", f"El primer pago debe ser como mínimo el valor de la matrícula: S/ {enrollment.enrollment_fee:.2f}.")
                    return self.form_invalid(form)
                installments = list(Installment.objects.select_for_update().filter(enrollment=enrollment, active=True).order_by("due_date", "id"))
                outstanding = [(i, i.balance) for i in installments if i.balance > 0]
                total_due = sum((balance for _, balance in outstanding), Decimal("0.00"))
                if total_due <= 0:
                    form.add_error(None, "Esta matrícula no tiene cuotas pendientes.")
                    return self.form_invalid(form)
                if amount > total_due:
                    form.add_error("amount", f"El importe supera la deuda pendiente (S/ {total_due:.2f}). Registre un importe menor o igual al saldo.")
                    return self.form_invalid(form)
                payment = Payment.objects.create(campus=campus, enrollment=enrollment, cashier=user, receipt_number=form.cleaned_data["receipt_number"].strip(), amount=amount, reference=form.cleaned_data["reference"], notes=form.cleaned_data["notes"])
                remaining = amount
                for installment, balance in outstanding:
                    if remaining <= 0:
                        break
                    applied = min(remaining, balance)
                    PaymentAllocation.objects.create(payment=payment, installment=installment, amount=applied)
                    remaining -= applied
        except IntegrityError:
            form.add_error(None, "No se pudo registrar el pago. Vuelva a intentarlo.")
            return self.form_invalid(form)
        messages.success(self.request, f"Pago registrado. Recibo {payment.receipt_number}.")
        return redirect("payment-receipt", pk=payment.pk)


class PaymentUpdateView(SelectedCampusViewMixin, UpdateView):
    model = Payment
    form_class = PaymentUpdateForm
    template_name = "payments/payment_form.html"
    success_url = reverse_lazy("payment-list")

    def get_queryset(self):
        return Payment.objects.filter(
            campus=get_selected_campus(self.request), status=Payment.Status.CONFIRMED
        ).select_related("enrollment__student", "enrollment__course")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        campus = get_selected_campus(self.request)
        selected_enrollment = form.cleaned_data["enrollment"]
        amount = form.cleaned_data["amount"]
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(
                pk=self.object.pk, campus=campus, status=Payment.Status.CONFIRMED
            )
            enrollment = Enrollment.objects.select_for_update().filter(
                pk=selected_enrollment.pk, campus=campus, active=True
            ).first()
            if enrollment is None:
                form.add_error("enrollment", "Selecciona una matrícula activa de esta sede.")
                return self.form_invalid(form)

            installments = list(
                Installment.objects.select_for_update()
                .filter(enrollment=enrollment, active=True)
                .order_by("due_date", "pk")
            )
            outstanding = []
            for installment in installments:
                paid_by_other_payments = PaymentAllocation.objects.filter(
                    installment=installment,
                    payment__status=Payment.Status.CONFIRMED,
                ).exclude(payment=payment).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                balance = installment.amount - paid_by_other_payments
                if balance > 0:
                    outstanding.append((installment, balance))

            total_due = sum((balance for _, balance in outstanding), Decimal("0.00"))
            has_other_confirmed_payments = Payment.objects.filter(
                enrollment=enrollment, status=Payment.Status.CONFIRMED
            ).exclude(pk=payment.pk).exists()
            if not has_other_confirmed_payments and amount < enrollment.enrollment_fee:
                form.add_error(
                    "amount",
                    f"El primer pago debe ser como mínimo el valor de la matrícula: S/ {enrollment.enrollment_fee:.2f}.",
                )
                return self.form_invalid(form)
            if total_due <= 0 or amount > total_due:
                form.add_error("amount", f"El importe no puede superar la deuda pendiente (S/ {total_due:.2f}).")
                return self.form_invalid(form)

            payment.receipt_number = form.cleaned_data["receipt_number"]
            payment.enrollment = enrollment
            payment.amount = amount
            payment.reference = form.cleaned_data["reference"]
            payment.notes = form.cleaned_data["notes"]
            payment.save(update_fields=["receipt_number", "enrollment", "amount", "reference", "notes"])
            PaymentAllocation.objects.filter(payment=payment).delete()
            remaining = amount
            for installment, balance in outstanding:
                if remaining <= 0:
                    break
                applied = min(remaining, balance)
                PaymentAllocation.objects.create(payment=payment, installment=installment, amount=applied)
                remaining -= applied

        self.object = payment
        messages.success(self.request, "Pago actualizado correctamente y sus cuotas fueron recalculadas.")
        return redirect(self.get_success_url())


class PaymentDeleteView(SelectedCampusViewMixin, DeleteView):
    model = Payment
    template_name = "payments/payment_confirm_delete.html"
    success_url = reverse_lazy("payment-list")

    def get_queryset(self):
        return Payment.objects.filter(
            campus=get_selected_campus(self.request), status=Payment.Status.CONFIRMED
        ).select_related("enrollment__student", "enrollment__course")

    def post(self, request, *args, **kwargs):
        payment = self.get_object()
        self.object = payment
        payment.status = Payment.Status.VOID
        payment.save(update_fields=["status"])
        messages.success(self.request, "Recibo anulado y conservado en el historial.")
        return redirect(self.get_success_url())


class PaymentReceiptView(SelectedCampusViewMixin, DetailView):
    model = Payment
    template_name = "payments/receipt.html"
    context_object_name = "payment"

    def get_queryset(self):
        return Payment.objects.filter(campus=get_selected_campus(self.request)).select_related("campus", "enrollment__student", "enrollment__course", "cashier").prefetch_related("allocations__installment")


class InstallmentListView(SelectedCampusViewMixin, ListView):
    model = Installment
    template_name = "payments/installment_list.html"
    context_object_name = "installments"
    paginate_by = 40

    def get_queryset(self):
        return Installment.objects.filter(active=True, enrollment__active=True, enrollment__campus=get_selected_campus(self.request)).select_related("enrollment__student", "enrollment__course", "enrollment__campus").order_by("due_date", "enrollment__student__full_name")


class PendingDebtsView(SelectedCampusViewMixin, ListView):
    """Reporte de cuotas con saldo pendiente, limitado a la sede seleccionada."""
    model = Installment
    template_name = "payments/pending_debts.html"
    context_object_name = "debts"
    paginate_by = 100

    def get_queryset(self):
        campus = get_selected_campus(self.request)
        paid_total = Coalesce(
            Sum(
                "allocations__amount",
                filter=Q(allocations__payment__status=Payment.Status.CONFIRMED),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        qs = (
            Installment.objects.filter(
                active=True, enrollment__active=True, enrollment__campus=campus
            )
            .annotate(paid_total=paid_total)
            .annotate(
                pending_balance=ExpressionWrapper(
                    F("amount") - F("paid_total"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .filter(pending_balance__gt=0)
            .select_related("enrollment__student", "enrollment__course", "enrollment__campus")
            .order_by("due_date", "enrollment__student__full_name")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(enrollment__student__full_name__icontains=q)
                | Q(enrollment__course__name__icontains=q)
                | Q(concept__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Suma de saldos pendientes para el conjunto filtrado, sin depender de la página actual.
        rows = self.get_queryset().values_list("pending_balance", flat=True)
        context["pending_grand_total"] = sum(rows, Decimal("0.00"))
        context["search_query"] = self.request.GET.get("q", "").strip()
        return context
