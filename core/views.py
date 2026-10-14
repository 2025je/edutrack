from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from .campus import available_campuses, get_selected_campus
from .models import Campus
from students.models import Student, Enrollment
from payments.models import Payment, Installment


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
            return redirect("dashboard")
    return render(request, "core/select_campus.html", {
        "campuses": campuses,
        "selected_campus": get_selected_campus(request),
    })


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
        can_manage_students = self.request.user.is_superuser or self.request.user.can_manage_students
        can_register_payments = self.request.user.is_superuser or self.request.user.can_register_payments
        if can_manage_students:
            ctx["student_count"] = Student.objects.filter(campus=campus).count()
            ctx["enrollment_count"] = Enrollment.objects.filter(campus=campus, active=True).count()
        if can_register_payments:
            ctx["payments_total"] = Payment.objects.filter(campus=campus, status=Payment.Status.CONFIRMED).aggregate(total=Sum("amount"))["total"] or 0
            ctx["pending_total"] = sum((i.balance for i in Installment.objects.filter(enrollment__campus=campus, active=True, enrollment__active=True)), start=0)
        return ctx
