import re
from decimal import Decimal
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import (
    Q,
    Sum,
    F,
    Value,
    DecimalField,
    ExpressionWrapper,
    Case,
    When,
    IntegerField,
    CharField,
)
from django.db.models.functions import Cast, Coalesce, Substr
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import (
    FormView,
    ListView,
    DetailView,
    UpdateView,
    DeleteView,
    TemplateView,
    View,
)
from core.campus import SelectedCampusRequiredMixin, FeaturePermissionMixin, get_selected_campus
from core.excel import xlsx_response
from core.pagination import paginate_context
from students.models import Course, Enrollment, Promoter
from .forms import (
    PaymentForm,
    PaymentUpdateForm,
    filter_pending_enrollments,
    pending_enrollments_for_campus,
)
from .models import (
    CashClosing,
    Installment,
    Payment,
    PaymentAllocation,
    is_cash_closed,
    receipt_number_validator,
)


MAX_RECEIPT_CHECK_RANGE = 10_000


def parse_receipt_code(value):
    receipt_number = value.strip().upper()
    receipt_number_validator(receipt_number)
    match = re.fullmatch(r"([A-Z]?)(\d+)", receipt_number)
    return match.group(1), int(match.group(2))


class SelectedCampusViewMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    required_permission = "payments.view_payment"


class PaymentListView(SelectedCampusViewMixin, ListView):
    model = Payment
    template_name = "payments/payment_list.html"
    context_object_name = "payments"
    paginate_by = 30
    sortable_fields = {
        "receipt": "receipt_number",
        "student": "enrollment__student__full_name",
        "date": "created_at",
        "cashier": "cashier__username",
        "amount": "amount",
        "status": "status",
    }

    def get_queryset(self):
        qs = Payment.objects.filter(campus=get_selected_campus(self.request)).select_related(
            "campus", "enrollment__student", "enrollment__course", "cashier"
        )
        receipt = self.request.GET.get("receipt", "").strip()
        student = self.request.GET.get("student", "").strip()
        if receipt:
            qs = qs.filter(receipt_number__wild=receipt)
        if student:
            qs = qs.filter(enrollment__student__full_name__unaccent__wild=student)
        for parameter, lookup in (
            ("date_from", "created_at__date__gte"),
            ("date_to", "created_at__date__lte"),
        ):
            value = self.request.GET.get(parameter, "").strip()
            if value:
                parsed_date = parse_date(value)
                qs = qs.filter(**{lookup: parsed_date}) if parsed_date else qs.none()
        status = self.request.GET.get("status", "")
        if status in Payment.Status.values:
            qs = qs.filter(status=status)
        course = self.request.GET.get("course", "").strip()
        if course:
            qs = qs.filter(enrollment__course__name__unaccent__wild=course)
        cashier = self.request.GET.get("cashier", "").strip()
        if cashier:
            qs = qs.filter(cashier__username__wild=cashier)
        reference = self.request.GET.get("reference", "").strip()
        if reference:
            qs = qs.filter(reference__wild=reference)
        for parameter, lookup in (("amount_min", "amount__gte"), ("amount_max", "amount__lte")):
            value = self.request.GET.get(parameter, "").strip()
            if value:
                try:
                    qs = qs.filter(**{lookup: Decimal(value)})
                except ArithmeticError:
                    qs = qs.none()

        sort = self.request.GET.get("sort", "date")
        direction = self.request.GET.get("direction", "desc")
        if direction not in {"asc", "desc"}:
            direction = "desc"
        if sort == "receipt":
            numeric_receipt = Q(receipt_number__regex=r"^\d+$")
            lettered_receipt = Q(receipt_number__regex=r"^[A-Z]\d+$")
            qs = qs.annotate(
                receipt_type=Case(
                    When(numeric_receipt, then=Value(0)),
                    When(lettered_receipt, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                receipt_letter=Case(
                    When(numeric_receipt, then=Value("")),
                    When(lettered_receipt, then=Substr("receipt_number", 1, 1)),
                    default=F("receipt_number"),
                    output_field=CharField(),
                ),
                receipt_sequence=Case(
                    When(numeric_receipt, then=Cast("receipt_number", IntegerField())),
                    When(lettered_receipt, then=Cast(Substr("receipt_number", 2), IntegerField())),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            receipt_order = ["receipt_type", "receipt_letter", "receipt_sequence", "pk"]
            if direction == "desc":
                receipt_order = [f"-{field}" for field in receipt_order]
            return qs.order_by(*receipt_order)
        sort_field = self.sortable_fields.get(sort, "created_at")
        if direction == "desc":
            sort_field = f"-{sort_field}"
        return qs.order_by(sort_field, "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["pagination_query"] = query_params.urlencode()
        context["current_sort"] = self.request.GET.get("sort", "date")
        context["current_direction"] = self.request.GET.get("direction", "desc")
        context["sort_urls"] = {}
        for key in self.sortable_fields:
            sort_params = self.request.GET.copy()
            sort_params.pop("page", None)
            if context["current_sort"] == key:
                next_direction = "desc" if context["current_direction"] == "asc" else "asc"
            else:
                next_direction = "asc"
            sort_params["sort"] = key
            sort_params["direction"] = next_direction
            context["sort_urls"][key] = f"?{sort_params.urlencode()}"
        page_start = context["page_obj"].start_index() if context.get("is_paginated") else 1
        for offset, payment in enumerate(context["payments"]):
            payment.row_number = page_start + offset
        return context


class PaymentSelectView(SelectedCampusViewMixin, TemplateView):
    required_permission = "payments.add_payment"
    """Paso previo: buscar la matrícula con deuda y elegir cuál pagar."""

    template_name = "payments/payment_select.html"

    def get(self, request, *args, **kwargs):
        # Compatibilidad con los enlaces antiguos ?enrollment=<id>.
        enrollment_id = request.GET.get("enrollment", "").strip()
        if enrollment_id.isdigit():
            return redirect("payment-create-for", enrollment_id=int(enrollment_id))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        base = pending_enrollments_for_campus(campus)
        rows = (
            filter_pending_enrollments(base, self.request.GET)
            .select_related("student", "course")
            .prefetch_related("promoter")
            .order_by("student__full_name", "course__name")
        )
        context.update(paginate_context(self.request, rows, per_page=15))
        context["enrollments"] = context["page_obj"].object_list
        context["filter_courses"] = (
            Course.objects.filter(enrollments__in=base).distinct().order_by("name", "schedule")
        )
        context["filter_promoters"] = (
            Promoter.objects.filter(enrollments__in=base).distinct().order_by("name")
        )
        filter_names = (
            "q",
            "dni",
            "course",
            "promoter",
            "schedule",
            "group",
            "ficha",
            "date_from",
            "date_to",
            "debt_min",
            "debt_max",
            "student",
        )
        context["has_filters"] = any(self.request.GET.get(name) for name in filter_names)
        context["more_filters_open"] = any(
            self.request.GET.get(name)
            for name in (
                "schedule",
                "group",
                "ficha",
                "date_from",
                "date_to",
                "debt_min",
                "debt_max",
            )
        )
        return context


class PaymentCreateView(SelectedCampusViewMixin, FormView):
    required_permission = "payments.add_payment"
    template_name = "payments/payment_form.html"
    form_class = PaymentForm
    success_url = reverse_lazy("payment-list")

    def _load_enrollment(self):
        campus = get_selected_campus(self.request)
        self.pending_enrollment = (
            pending_enrollments_for_campus(campus)
            .select_related("student", "course")
            .filter(pk=self.kwargs["enrollment_id"])
            .first()
            if campus
            else None
        )
        if self.pending_enrollment is None:
            messages.warning(
                self.request, "Esa matrícula no tiene deuda pendiente o no está disponible."
            )
            return redirect("payment-create")
        return None

    def get(self, request, *args, **kwargs):
        return self._load_enrollment() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        if campus and is_cash_closed(campus.pk, timezone.localdate()):
            messages.error(
                request, "La caja de hoy está cerrada; no se pueden registrar más pagos."
            )
            return redirect("payment-list")
        return self._load_enrollment() or super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["enrollment"] = self.pending_enrollment
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        kwargs["enrollment"] = self.pending_enrollment
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["enrollment"] = self.pending_enrollment.pk
        initial["amount"] = self.pending_enrollment.pending_balance
        return initial

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

                enrollment = Enrollment.objects.select_for_update(of=("self",)).get(
                    pk=enrollment.pk, campus=campus
                )
                has_confirmed_payment = Payment.objects.filter(
                    enrollment=enrollment, status=Payment.Status.CONFIRMED
                ).exists()
                if not has_confirmed_payment and amount < enrollment.enrollment_fee:
                    form.add_error(
                        "amount",
                        f"El primer pago debe ser como mínimo el valor de la matrícula: S/ {enrollment.enrollment_fee:.2f}.",
                    )
                    return self.form_invalid(form)
                installments = list(
                    Installment.objects.select_for_update()
                    .filter(enrollment=enrollment, active=True)
                    .order_by("due_date", "id")
                )
                outstanding = [(i, i.balance) for i in installments if i.balance > 0]
                total_due = sum((balance for _, balance in outstanding), Decimal("0.00"))
                if total_due <= 0:
                    form.add_error(None, "Esta matrícula no tiene cuotas pendientes.")
                    return self.form_invalid(form)
                if amount > total_due:
                    form.add_error(
                        "amount",
                        f"El importe supera la deuda pendiente (S/ {total_due:.2f}). Registre un importe menor o igual al saldo.",
                    )
                    return self.form_invalid(form)
                payment = Payment.objects.create(
                    campus=campus,
                    enrollment=enrollment,
                    cashier=user,
                    receipt_number=form.cleaned_data["receipt_number"].strip(),
                    amount=amount,
                    reference=form.cleaned_data["reference"],
                    notes=form.cleaned_data["notes"],
                    voucher=form.voucher_file() or "",
                )
                remaining = amount
                for installment, balance in outstanding:
                    if remaining <= 0:
                        break
                    applied = min(remaining, balance)
                    PaymentAllocation.objects.create(
                        payment=payment, installment=installment, amount=applied
                    )
                    remaining -= applied
        except IntegrityError:
            form.add_error(None, "No se pudo registrar el pago. Vuelva a intentarlo.")
            return self.form_invalid(form)
        messages.success(self.request, f"Pago registrado. Recibo {payment.receipt_number}.")
        return redirect("payment-receipt", pk=payment.pk)


class ClosedCashGuardMixin:
    """Impide editar o anular pagos de un día cuya caja ya fue cerrada."""

    def locked_response(self):
        payment = self.get_object()
        day = timezone.localtime(payment.created_at).date()
        if is_cash_closed(payment.campus_id, day):
            messages.error(
                self.request,
                f"La caja del {day:%d/%m/%Y} está cerrada; sus pagos ya no se pueden modificar.",
            )
            return redirect("payment-list")
        return None

    def get(self, request, *args, **kwargs):
        return self.locked_response() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.locked_response() or super().post(request, *args, **kwargs)


class PaymentUpdateView(ClosedCashGuardMixin, SelectedCampusViewMixin, UpdateView):
    required_permission = "payments.change_payment"
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
            enrollment = (
                Enrollment.objects.select_for_update(of=("self",))
                .filter(pk=selected_enrollment.pk, campus=campus, active=True)
                .first()
            )
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
                ).exclude(payment=payment).aggregate(total=Sum("amount"))["total"] or Decimal(
                    "0.00"
                )
                balance = installment.amount - paid_by_other_payments
                if balance > 0:
                    outstanding.append((installment, balance))

            total_due = sum((balance for _, balance in outstanding), Decimal("0.00"))
            has_other_confirmed_payments = (
                Payment.objects.filter(enrollment=enrollment, status=Payment.Status.CONFIRMED)
                .exclude(pk=payment.pk)
                .exists()
            )
            if not has_other_confirmed_payments and amount < enrollment.enrollment_fee:
                form.add_error(
                    "amount",
                    f"El primer pago debe ser como mínimo el valor de la matrícula: S/ {enrollment.enrollment_fee:.2f}.",
                )
                return self.form_invalid(form)
            if total_due <= 0 or amount > total_due:
                form.add_error(
                    "amount",
                    f"El importe no puede superar la deuda pendiente (S/ {total_due:.2f}).",
                )
                return self.form_invalid(form)

            payment.receipt_number = form.cleaned_data["receipt_number"]
            payment.enrollment = enrollment
            payment.amount = amount
            payment.reference = form.cleaned_data["reference"]
            payment.notes = form.cleaned_data["notes"]
            old_voucher = payment.voucher.name
            new_voucher = form.voucher_file()
            fields = ["receipt_number", "enrollment", "amount", "reference", "notes"]
            if new_voucher is not None:
                payment.voucher = new_voucher or ""
                fields.append("voucher")
            payment.save(update_fields=fields)
            if new_voucher is not None and old_voucher and old_voucher != payment.voucher.name:
                storage = payment.voucher.storage
                transaction.on_commit(lambda: storage.delete(old_voucher))
            PaymentAllocation.objects.filter(payment=payment).delete()
            remaining = amount
            for installment, balance in outstanding:
                if remaining <= 0:
                    break
                applied = min(remaining, balance)
                PaymentAllocation.objects.create(
                    payment=payment, installment=installment, amount=applied
                )
                remaining -= applied

        self.object = payment
        messages.success(
            self.request, "Pago actualizado correctamente y sus cuotas fueron recalculadas."
        )
        return redirect(self.get_success_url())


class PaymentDeleteView(ClosedCashGuardMixin, SelectedCampusViewMixin, DeleteView):
    required_permission = "core.void_payment"
    model = Payment
    template_name = "payments/payment_confirm_delete.html"
    success_url = reverse_lazy("payment-list")

    def get_queryset(self):
        return Payment.objects.filter(
            campus=get_selected_campus(self.request), status=Payment.Status.CONFIRMED
        ).select_related("enrollment__student", "enrollment__course")

    def post(self, request, *args, **kwargs):
        locked = self.locked_response()
        if locked:
            return locked
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
        return (
            Payment.objects.filter(campus=get_selected_campus(self.request))
            .select_related("campus", "enrollment__student", "enrollment__course", "cashier")
            .prefetch_related("allocations__installment")
        )


class InstallmentListView(SelectedCampusViewMixin, ListView):
    required_permission = "core.view_pending_balances"
    model = Installment
    template_name = "payments/installment_list.html"
    context_object_name = "installments"
    paginate_by = 40

    def get_queryset(self):
        return (
            Installment.objects.filter(
                active=True,
                enrollment__active=True,
                enrollment__campus=get_selected_campus(self.request),
            )
            .select_related("enrollment__student", "enrollment__course", "enrollment__campus")
            .order_by("due_date", "enrollment__student__full_name")
        )


class PendingDebtsView(SelectedCampusViewMixin, ListView):
    required_permission = "core.view_pending_balances"
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
        if self.request.GET.get("vencidas") == "1":
            qs = qs.filter(due_date__lt=timezone.localdate())
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(enrollment__student__full_name__unaccent__wild=q)
                | Q(enrollment__course__name__unaccent__wild=q)
                | Q(concept__unaccent__wild=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Suma de saldos pendientes para el conjunto filtrado, sin depender de la página actual.
        rows = self.get_queryset().values_list("pending_balance", flat=True)
        context["pending_grand_total"] = sum(rows, Decimal("0.00"))
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["only_overdue"] = self.request.GET.get("vencidas") == "1"
        params = self.request.GET.copy()
        params.pop("page", None)
        context["pagination_query"] = params.urlencode()
        if self.request.user.has_perm("calls.view_callnote"):
            self.attach_reminders(context["debts"])
        return context

    def attach_reminders(self, debts):
        """Enlaces de WhatsApp con la plantilla de la sede para recordar cada cuota."""
        from calls.models import WhatsAppTemplate
        from calls.views import build_phone_links

        campus = get_selected_campus(self.request)
        template = WhatsAppTemplate.for_campus(campus)[WhatsAppTemplate.Kind.DEBT]
        for debt in debts:
            student = debt.enrollment.student
            debt.reminder_links = []
            if student is not None:
                courses = [{"course_label": debt.concept, "debt": debt.pending_balance}]
                debt.reminder_links = build_phone_links(
                    template, campus, student, courses, debt.pending_balance
                )


class PaymentExcelExportView(PaymentListView):
    """Exporta a Excel los pagos con los mismos filtros y orden del listado."""

    required_permission = ("payments.view_payment", "core.export_reports")

    def get(self, request, *args, **kwargs):
        self.request = request
        payments = self.get_queryset()
        rows = [
            [
                p.receipt_number,
                timezone.localtime(p.created_at).replace(tzinfo=None),
                p.enrollment.student_label,
                p.enrollment.course_label,
                p.amount,
                p.get_status_display(),
                p.cashier.get_full_name() or p.cashier.username,
                p.reference,
            ]
            for p in payments
        ]
        confirmed = sum(
            (p.amount for p in payments if p.status == Payment.Status.CONFIRMED), Decimal("0.00")
        )
        return xlsx_response(
            "pagos",
            "Pagos",
            f"Sede: {get_selected_campus(request).name}",
            [
                "N.º de recibo",
                "Fecha y hora",
                "Estudiante",
                "Curso",
                "Importe",
                "Estado",
                "Cajero",
                "Referencia",
            ],
            rows,
            money=(4,),
            dates=(1,),
            totals=["Total confirmado", "", "", "", confirmed, "", "", ""],
        )


class CashClosingView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Cierre de caja: pagos de un día agrupados por cajero (solo los confirmados suman)."""

    required_permission = ("payments.view_payment", "core.view_financial_reports")
    template_name = "payments/cash_closing.html"

    def get_day(self):
        return parse_date(self.request.GET.get("fecha", "")) or timezone.localdate()

    def get_payments(self):
        qs = Payment.objects.filter(
            campus=get_selected_campus(self.request), created_at__date=self.get_day()
        ).select_related("enrollment__student", "enrollment__course", "cashier")
        cashier = self.request.GET.get("cajero", "")
        if cashier.isdigit():
            qs = qs.filter(cashier_id=int(cashier))
        return qs.order_by("cashier__username", "created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payments = list(self.get_payments())
        groups = {}
        for payment in payments:
            group = groups.setdefault(
                payment.cashier_id,
                {
                    "cashier": payment.cashier.get_full_name() or payment.cashier.username,
                    "payments": [],
                    "confirmed": Decimal("0.00"),
                    "voided": Decimal("0.00"),
                },
            )
            group["payments"].append(payment)
            if payment.status == Payment.Status.CONFIRMED:
                group["confirmed"] += payment.amount
            else:
                group["voided"] += payment.amount
        cashiers = (
            Payment.objects.filter(campus=get_selected_campus(self.request))
            .values_list("cashier_id", "cashier__username")
            .distinct()
            .order_by("cashier__username")
        )
        closing = (
            CashClosing.objects.filter(
                campus=get_selected_campus(self.request), date=self.get_day()
            )
            .select_related("closed_by")
            .first()
        )
        context.update(
            day=self.get_day(),
            groups=list(groups.values()),
            total_confirmed=sum((g["confirmed"] for g in groups.values()), Decimal("0.00")),
            total_voided=sum((g["voided"] for g in groups.values()), Decimal("0.00")),
            cashiers=cashiers,
            cashier=self.request.GET.get("cajero", ""),
            closing=closing,
            can_close=(
                closing is None
                and self.get_day() <= timezone.localdate()
                and self.request.user.has_perm("core.close_cash")
            ),
        )
        return context


class CashClosingCloseView(FeaturePermissionMixin, SelectedCampusRequiredMixin, View):
    """Firma el cierre de caja de una fecha: congela sus totales y bloquea sus pagos."""

    required_permission = ("payments.view_payment", "core.close_cash")
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        day = parse_date(request.POST.get("fecha", ""))
        back = f"{reverse('cash-closing')}?fecha={day:%Y-%m-%d}" if day else reverse("cash-closing")
        if day is None or day > timezone.localdate():
            messages.error(request, "Elige una fecha válida (no futura) para cerrar la caja.")
            return redirect("cash-closing")
        payments = Payment.objects.filter(campus=campus, created_at__date=day)
        totals = payments.aggregate(
            confirmed=Sum("amount", filter=Q(status=Payment.Status.CONFIRMED)),
            voided=Sum("amount", filter=~Q(status=Payment.Status.CONFIRMED)),
        )
        with transaction.atomic():
            _, created = CashClosing.objects.get_or_create(
                campus=campus,
                date=day,
                defaults={
                    "confirmed_total": totals["confirmed"] or Decimal("0.00"),
                    "voided_total": totals["voided"] or Decimal("0.00"),
                    "payments_count": payments.count(),
                    "note": request.POST.get("nota", "").strip()[:255],
                    "closed_by": request.user,
                },
            )
        if created:
            messages.success(request, f"Caja del {day:%d/%m/%Y} cerrada.")
        else:
            messages.info(request, "Esa caja ya estaba cerrada.")
        return redirect(back)


class CashClosingReopenView(SelectedCampusRequiredMixin, View):
    """Solo un superusuario puede reabrir una caja cerrada."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("Solo un superusuario puede reabrir una caja.")
        closing = get_object_or_404(
            CashClosing, pk=request.POST.get("cierre"), campus=get_selected_campus(request)
        )
        day = closing.date
        closing.delete()
        messages.success(request, f"Caja del {day:%d/%m/%Y} reabierta.")
        return redirect(f"{reverse('cash-closing')}?fecha={day:%Y-%m-%d}")


class CashClosingExcelView(CashClosingView):
    required_permission = (
        "payments.view_payment",
        "core.view_financial_reports",
        "core.export_reports",
    )

    def get(self, request, *args, **kwargs):
        self.request = request
        payments = list(self.get_payments())
        rows = [
            [
                p.cashier.get_full_name() or p.cashier.username,
                p.receipt_number,
                timezone.localtime(p.created_at).replace(tzinfo=None),
                p.enrollment.student_label,
                p.enrollment.course_label,
                p.get_status_display(),
                p.amount,
            ]
            for p in payments
        ]
        confirmed = sum(
            (p.amount for p in payments if p.status == Payment.Status.CONFIRMED), Decimal("0.00")
        )
        return xlsx_response(
            f"cierre-caja-{self.get_day():%Y-%m-%d}",
            "Cierre de caja",
            f"Sede: {get_selected_campus(request).name} · {self.get_day():%d/%m/%Y}",
            ["Cajero", "N.º de recibo", "Fecha y hora", "Estudiante", "Curso", "Estado", "Importe"],
            rows,
            money=(6,),
            dates=(2,),
            totals=["Total confirmado", "", "", "", "", "", confirmed],
        )


class PendingDebtsExcelView(PendingDebtsView):
    """Exporta a Excel las cuotas con saldo pendiente (según la búsqueda actual)."""

    required_permission = ("core.view_pending_balances", "core.export_reports")

    def get(self, request, *args, **kwargs):
        self.request = request
        debts = list(self.get_queryset())
        rows = [
            [
                d.enrollment.student_label,
                d.enrollment.student.phone if d.enrollment.student_id else "",
                d.enrollment.course_label,
                d.concept,
                d.due_date,
                d.amount,
                d.paid_total,
                d.pending_balance,
            ]
            for d in debts
        ]
        total = sum((d.pending_balance for d in debts), Decimal("0.00"))
        return xlsx_response(
            "deudas_pendientes",
            "Deudas pendientes",
            f"Sede: {get_selected_campus(request).name}",
            [
                "Estudiante",
                "Celular",
                "Curso / grupo",
                "Concepto",
                "Vencimiento",
                "Importe",
                "Pagado",
                "Saldo pendiente",
            ],
            rows,
            money=(5, 6, 7),
            dates=(4,),
            totals=["Saldo pendiente total", "", "", "", "", "", "", total],
        )


class EnrollmentStatementView(SelectedCampusViewMixin, DetailView):
    """Estado de cuenta imprimible de una matrícula: cuotas, pagos y saldo."""

    model = Enrollment
    template_name = "payments/statement.html"
    context_object_name = "enrollment"
    pk_url_kwarg = "enrollment_id"

    def get_queryset(self):
        return Enrollment.objects.filter(campus=get_selected_campus(self.request)).select_related(
            "student", "course", "campus"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollment = self.object
        paid_by_installment = dict(
            PaymentAllocation.objects.filter(
                installment__enrollment=enrollment, payment__status=Payment.Status.CONFIRMED
            )
            .values_list("installment")
            .annotate(total=Sum("amount"))
        )
        today = timezone.localdate()
        rows = []
        for installment in enrollment.installments.filter(active=True).order_by("due_date", "id"):
            paid = paid_by_installment.get(installment.pk, Decimal("0.00"))
            balance = installment.amount - paid
            rows.append(
                {
                    "installment": installment,
                    "paid": paid,
                    "balance": balance,
                    "overdue": balance > 0 and installment.due_date < today,
                }
            )
        context.update(
            rows=rows,
            total_billed=sum((r["installment"].amount for r in rows), Decimal("0.00")),
            total_paid=sum((r["paid"] for r in rows), Decimal("0.00")),
            total_balance=sum((r["balance"] for r in rows), Decimal("0.00")),
            payments=enrollment.payments.select_related("cashier").order_by("created_at"),
            today=today,
        )
        return context
