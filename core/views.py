from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Permission
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db.models import F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView
from .campus import available_campuses, get_selected_campus
from .permission_labels import describe
from django.contrib.auth import get_user_model
from django.utils import timezone
from students.models import Student, Enrollment, Course, Promoter
from payments.models import Payment, PaymentAllocation, Installment

User = get_user_model()


class ProfileView(LoginRequiredMixin, PasswordChangeView):
    """Perfil del usuario: datos de la cuenta, grupos, permisos y cambio de contraseña."""

    template_name = "core/profile.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("profile")

    def form_valid(self, form):
        messages.success(self.request, "Contraseña actualizada correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        permissions = (
            Permission.objects.filter(Q(group__user=user) | Q(user=user))
            .distinct()
            .select_related("content_type")
            .order_by("content_type__app_label", "codename")
        )
        modules = {}
        for perm in permissions:
            module, name, detail = describe(perm)
            modules.setdefault(module, []).append({"name": name, "detail": detail})
        context.update(
            groups=user.groups.order_by("name"),
            permission_modules=[] if user.is_superuser else sorted(modules.items()),
            campuses=user.campuses.order_by("name"),
        )
        return context


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
        can_see_enrollments = self.request.user.has_perm("students.view_enrollment")
        can_see_financials = self.request.user.has_perm("core.view_financial_reports")
        can_see_payments = self.request.user.has_perm("payments.view_payment")
        user = self.request.user
        today = timezone.localdate()
        month_start = today.replace(day=1)
        if can_see_enrollments:
            enrollments = Enrollment.objects.filter(campus=campus, active=True)
            ctx["student_count"] = Student.objects.filter(campus=campus).count()
            ctx["enrollment_count"] = enrollments.count()
            ctx["enrollments_month"] = enrollments.filter(enrollment_date__gte=month_start).count()
            ctx["enrollments_today"] = enrollments.filter(enrollment_date=today).count()
            ctx["ficha_count"] = enrollments.filter(ficha__isnull=False).count()
            ctx["recent_enrollments"] = enrollments.select_related("student", "course").order_by(
                "-created_at"
            )[:5]
        confirmed = Payment.objects.filter(campus=campus, status=Payment.Status.CONFIRMED)
        if can_see_financials:
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
            installments = Installment.objects.filter(
                enrollment__campus=campus, active=True, enrollment__active=True
            ).annotate(
                paid_total=Coalesce(
                    Subquery(
                        PaymentAllocation.objects.filter(
                            installment=OuterRef("pk"), payment__status=Payment.Status.CONFIRMED
                        )
                        .values("installment")
                        .annotate(t=Sum("amount"))
                        .values("t")[:1]
                    ),
                    Value(Decimal("0.00")),
                )
            )
            totals = installments.aggregate(total=Sum("amount"), paid=Sum("paid_total"))
            ctx["pending_total"] = (totals["total"] or 0) - (totals["paid"] or 0)
            ctx["overdue_count"] = installments.filter(
                due_date__lt=today, paid_total__lt=F("amount")
            ).count()
        if can_see_payments:
            ctx["recent_payments"] = confirmed.select_related("enrollment__student").order_by(
                "-created_at"
            )[:5]
        if user.has_perm("calls.view_callnote"):
            from calls.models import CallNote
            from calls.views import can_view_all_calls, visible_enrollments

            notes = CallNote.objects.filter(campus=campus)
            if not can_view_all_calls(user):
                notes = notes.filter(author=user)
            ctx["call_enrollments"] = visible_enrollments(self.request).count()
            ctx["calls_today"] = notes.filter(created_at__date=today).count()
            ctx["calls_month"] = notes.filter(created_at__date__gte=month_start).count()
            ctx["calls_scope_all"] = can_view_all_calls(user)
        if user.has_perm("students.view_course"):
            ctx["course_count"] = Course.objects.filter(campus=campus, active=True).count()
        if user.has_perm("students.view_promoter"):
            ctx["promoter_count"] = Promoter.objects.filter(campuses=campus, active=True).count()
        if user.has_perm("core.view_user"):
            ctx["user_count"] = User.objects.filter(is_active=True).count()
        return ctx


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = "core/search.html"
    limit = 15

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not (
            user.has_perm("students.view_student") or user.has_perm("payments.view_payment")
        ):
            raise PermissionDenied("No tienes permiso para usar la búsqueda.")
        if user.is_authenticated and get_selected_campus(request) is None:
            return redirect("select-campus")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from students.models import Ficha

        context = super().get_context_data(**kwargs)
        user = self.request.user
        campus = get_selected_campus(self.request)
        q = self.request.GET.get("q", "").strip()[:80]
        can_students = user.has_perm("students.view_student")
        can_payments = user.has_perm("payments.view_payment")
        context.update(q=q, can_students=can_students, can_payments=can_payments)
        students = fichas = payments = []
        if q:
            if can_students:
                students = list(
                    Student.objects.filter(campus=campus)
                    .filter(Q(full_name__unaccent__icontains=q) | Q(document_number__icontains=q))
                    .order_by("full_name")[: self.limit]
                )
                if q.isdigit() and user.has_perm("students.view_enrollment"):
                    fichas = list(
                        Ficha.objects.filter(campus=campus, code=int(q))
                        .select_related("enrollment__student", "enrollment__course")
                        .order_by("-date")[: self.limit]
                    )
            if can_payments:
                payments = list(
                    Payment.objects.filter(campus=campus, receipt_number__icontains=q)
                    .select_related("enrollment__student")
                    .order_by("-created_at")[: self.limit]
                )
        context.update(students=students, fichas=fichas, payments=payments)
        context["total"] = len(students) + len(fichas) + len(payments)
        return context
