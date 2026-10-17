from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView
from .campus import available_campuses, get_selected_campus
from django.contrib.auth import get_user_model
from django.utils import timezone
from students.models import Student, Enrollment, Course, Promoter
from payments.models import Payment, Installment

User = get_user_model()


@login_required
def select_campus(request):
    campuses = available_campuses(request.user)
    if request.method == "POST":
        campus_id = request.POST.get("campus")
        campus = campuses.filter(pk=campus_id).first()
        if campus is None:
            messages.error(request, "Selecciona una sede activa a la que tengas acceso.")
        else:
            request.session["selected_campus_id"] = campus.pk
            messages.success(request, f"Sede seleccionada: {campus.name}.")
            next_url = request.POST.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect("dashboard")
    return render(
        request,
        "core/select_campus.html",
        {
            "campuses": campuses,
            "selected_campus": get_selected_campus(request),
        },
    )


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and get_selected_campus(request) is None:
            return redirect("select-campus")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        ctx["selected_campus"] = campus
        ctx["campuses"] = available_campuses(self.request.user)
        can_manage_students = (
            self.request.user.is_superuser or self.request.user.can_manage_students
        )
        can_register_payments = (
            self.request.user.is_superuser or self.request.user.can_register_payments
        )
        user = self.request.user
        today = timezone.localdate()
        month_start = today.replace(day=1)
        if can_manage_students:
            enrollments = Enrollment.objects.filter(campus=campus, active=True)
            ctx["student_count"] = Student.objects.filter(campus=campus).count()
            ctx["enrollment_count"] = enrollments.count()
            ctx["enrollments_month"] = enrollments.filter(enrollment_date__gte=month_start).count()
            ctx["enrollments_today"] = enrollments.filter(enrollment_date=today).count()
            ctx["ficha_count"] = enrollments.filter(ficha__isnull=False).count()
            ctx["recent_enrollments"] = enrollments.select_related("student", "course").order_by(
                "-created_at"
            )[:5]
        if can_register_payments:
            confirmed = Payment.objects.filter(campus=campus, status=Payment.Status.CONFIRMED)
            ctx["payments_total"] = confirmed.aggregate(total=Sum("amount"))["total"] or 0
            ctx["payments_today"] = (
                confirmed.filter(created_at__date=today).aggregate(total=Sum("amount"))["total"]
                or 0
            )
            ctx["payments_month"] = (
                confirmed.filter(created_at__date__gte=month_start).aggregate(total=Sum("amount"))[
                    "total"
                ]
                or 0
            )
            pending_total = 0
            overdue_count = 0
            for i in Installment.objects.filter(
                enrollment__campus=campus, active=True, enrollment__active=True
            ):
                balance = i.balance
                pending_total += balance
                if balance > 0 and i.due_date < today:
                    overdue_count += 1
            ctx["pending_total"] = pending_total
            ctx["overdue_count"] = overdue_count
            ctx["recent_payments"] = confirmed.select_related("enrollment__student").order_by(
                "-created_at"
            )[:5]
        if user.is_superuser or user.can_manage_calls:
            from calls.models import CallNote
            from calls.views import can_view_all_calls, visible_enrollments

            notes = CallNote.objects.filter(campus=campus)
            if not can_view_all_calls(user):
                notes = notes.filter(author=user)
            ctx["call_enrollments"] = visible_enrollments(self.request).count()
            ctx["calls_today"] = notes.filter(created_at__date=today).count()
            ctx["calls_month"] = notes.filter(created_at__date__gte=month_start).count()
            ctx["calls_scope_all"] = can_view_all_calls(user)
        if user.is_superuser or user.can_manage_promoters:
            ctx["course_count"] = Course.objects.filter(campus=campus, active=True).count()
            ctx["promoter_count"] = Promoter.objects.filter(campuses=campus, active=True).count()
        if user.is_superuser or user.can_manage_users:
            ctx["user_count"] = User.objects.filter(is_active=True).count()
        return ctx
