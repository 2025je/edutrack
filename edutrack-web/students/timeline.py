from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from calls.models import CallNote
from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import ActivityLog
from payments.models import Payment

from .models import Enrollment, Student

MAX_EVENTS = 300


def student_events(user, campus, student, enrollments):
    """Eventos del estudiante ordenados del más reciente al más antiguo, con quién los hizo."""
    ids = [e.pk for e in enrollments]
    events = [
        {
            "when": e.created_at,
            "icon": "assignment",
            "kind": "Matrícula",
            "text": f"Matriculado en {e.course_label}" + ("" if e.active else " (inactiva)"),
            "who": "",
        }
        for e in enrollments
    ]
    if user.has_perm("payments.view_payment"):
        payments = Payment.objects.filter(enrollment__in=ids).select_related(
            "cashier", "enrollment__course"
        )
        events += [
            {
                "when": p.created_at,
                "icon": "payments",
                "kind": "Pago",
                "text": (
                    f"Recibo {p.receipt_number}: S/ {p.amount:.2f} en "
                    f"{p.enrollment.course_label} ({p.get_status_display()})"
                ),
                "who": p.cashier.username,
            }
            for p in payments
        ]
    if user.has_perm("calls.view_callnote"):
        notes = CallNote.objects.filter(student=student, campus=campus).select_related("author")
        events += [
            {
                "when": n.created_at,
                "icon": "call",
                "kind": "Llamada",
                "text": (
                    f"{n.get_response_display()}: {n.note}"
                    + (f" · Pagará el {n.promise_date:%d/%m/%Y}" if n.promise_date else "")
                ),
                "who": n.author.username if n.author_id else "",
            }
            for n in notes
        ]
    logs = ActivityLog.objects.filter(
        Q(object_type="student", object_id=student.pk)
        | Q(object_type="enrollment", object_id__in=ids)
    ).select_related("user")
    events += [
        {
            "when": log.created_at,
            "icon": "history",
            "kind": "Cambio",
            "text": log.description,
            "who": log.username,
        }
        for log in logs
    ]
    events.sort(key=lambda event: event["when"], reverse=True)
    return events


class StudentTimelineView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Línea de tiempo del estudiante: matrículas, pagos, llamadas y cambios registrados."""

    required_permission = "students.view_student"
    template_name = "students/timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        student = get_object_or_404(Student, pk=self.kwargs["pk"], campus=campus)
        enrollments = list(
            Enrollment.objects.filter(student=student, campus=campus).select_related("course")
        )
        events = student_events(self.request.user, campus, student, enrollments)
        context.update(
            student=student, events=events[:MAX_EVENTS], truncated=len(events) > MAX_EVENTS
        )
        return context
