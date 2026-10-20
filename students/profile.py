from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView

from calls.models import CallNote
from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from payments.models import Payment, PaymentAllocation

from .models import Enrollment, Student
from .timeline import MAX_EVENTS, student_events

ZERO = Decimal("0.00")


def installment_rows(enrollment_ids):
    """Cuotas activas agrupadas por matrícula, con lo pagado (solo pagos confirmados) y su estado."""
    from payments.models import Installment

    paid = dict(
        PaymentAllocation.objects.filter(
            installment__enrollment__in=enrollment_ids, payment__status=Payment.Status.CONFIRMED
        )
        .values_list("installment")
        .annotate(total=Sum("amount"))
    )
    today = timezone.localdate()
    grouped = {pk: [] for pk in enrollment_ids}
    for installment in Installment.objects.filter(
        enrollment__in=enrollment_ids, active=True
    ).order_by("due_date", "id"):
        paid_amount = paid.get(installment.pk, ZERO)
        balance = installment.amount - paid_amount
        if balance <= 0:
            state, color = "Pagada", "green"
        elif installment.due_date < today:
            state, color = "Vencida", "red"
        else:
            state, color = "Pendiente", "orange"
        grouped[installment.enrollment_id].append(
            {
                "installment": installment,
                "paid": paid_amount,
                "balance": balance,
                "state": state,
                "color": color,
            }
        )
    return grouped


class StudentProfileView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Ficha integral: datos, teléfonos, matrículas, cuotas, pagos, documentos e historial."""

    required_permission = "students.view_student"
    template_name = "students/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        campus = get_selected_campus(self.request)
        student = get_object_or_404(
            Student.objects.prefetch_related("phones"), pk=self.kwargs["pk"], campus=campus
        )
        enrollments = list(
            Enrollment.objects.filter(student=student, campus=campus)
            .select_related("course", "ficha")
            .prefetch_related("promoter")
            .order_by("-active", "-enrollment_date", "-id")
        )
        ids = [e.pk for e in enrollments]
        can_installments = user.has_perm("core.view_pending_balances")
        can_payments = user.has_perm("payments.view_payment")
        can_notes = user.has_perm("calls.view_callnote")

        installments = installment_rows(ids) if can_installments else {}
        payments = {pk: [] for pk in ids}
        if can_payments:
            for payment in Payment.objects.filter(enrollment__in=ids).select_related("cashier"):
                payments[payment.enrollment_id].append(payment)

        cards = []
        documents = []
        for enrollment in enrollments:
            rows = installments.get(enrollment.pk, [])
            enrollment_payments = payments[enrollment.pk]
            cards.append(
                {
                    "enrollment": enrollment,
                    "installments": rows,
                    "payments": enrollment_payments,
                    "total": sum((r["installment"].amount for r in rows), ZERO),
                    "paid": sum((r["paid"] for r in rows), ZERO),
                    "balance": sum((r["balance"] for r in rows), ZERO),
                }
            )
            ficha = getattr(enrollment, "ficha", None)
            if ficha and ficha.image:
                documents.append(
                    {
                        "kind": "Ficha",
                        "label": f"Ficha {ficha.code} · {enrollment.course_label}",
                        "url": ficha.image.url,
                        "when": ficha.updated_at,
                    }
                )
            for payment in enrollment_payments:
                if payment.voucher:
                    documents.append(
                        {
                            "kind": "Voucher",
                            "label": f"Recibo {payment.receipt_number}",
                            "url": payment.voucher.url,
                            "when": payment.created_at,
                        }
                    )
        documents.sort(key=lambda doc: doc["when"], reverse=True)

        notes = (
            CallNote.objects.filter(student=student, campus=campus).select_related("author")
            if can_notes
            else []
        )
        events = student_events(user, campus, student, enrollments)
        context.update(
            student=student,
            phones=list(student.phones.all()),
            current=[c for c in cards if c["enrollment"].active],
            previous=[c for c in cards if not c["enrollment"].active],
            documents=documents,
            notes=notes,
            events=events[:MAX_EVENTS],
            truncated=len(events) > MAX_EVENTS,
            can_installments=can_installments,
            can_payments=can_payments,
            can_notes=can_notes,
        )
        return context
