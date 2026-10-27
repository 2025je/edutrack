"""Traslado de curso y papelera (restauración de bajas)."""

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from core.campus import get_selected_campus
from payments.models import Installment, Payment

from .installments import fee_conflicts, sync_initial_installments
from .models import Course, Enrollment, Student
from .views import CampusScopedMixin, seats_message

TRASH_LIMIT = 200


class CourseChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, course):
        capacity = course.capacity
        seats = "sin límite" if not capacity else f"{max(capacity - course.occupied, 0)} vacantes"
        return f"{course} · {seats}"


class EnrollmentTransferForm(forms.Form):
    course = CourseChoiceField(queryset=Course.objects.none(), label="Nuevo curso")
    use_course_fees = forms.BooleanField(
        label="Usar los costos del nuevo curso",
        required=False,
        initial=True,
        help_text="Si no se marca, se conservan los costos actuales de la matrícula.",
    )

    def __init__(self, *args, enrollment, **kwargs):
        super().__init__(*args, **kwargs)
        courses = Course.objects.filter(campus=enrollment.campus, active=True)
        if enrollment.course_id:
            courses = courses.exclude(pk=enrollment.course_id)
        if enrollment.student_id:
            taken = Enrollment.objects.filter(
                student_id=enrollment.student_id, course__isnull=False
            ).values_list("course_id", flat=True)
            courses = courses.exclude(pk__in=taken)
        self.fields["course"].queryset = courses.annotate(
            occupied=Count(
                "enrollments",
                filter=Q(enrollments__active=True)
                & (Q(enrollments__student__isnull=True) | Q(enrollments__student__active=True)),
            )
        ).order_by("name", "schedule", "group")


class EnrollmentTransferView(CampusScopedMixin, TemplateView):
    required_permission = "core.change_enrollment_course"
    template_name = "students/enrollment_transfer.html"

    def get_enrollment(self):
        return get_object_or_404(
            Enrollment.objects.select_related("campus", "student", "course"),
            pk=self.kwargs["pk"],
            campus=get_selected_campus(self.request),
            active=True,
        )

    def render(self, enrollment, form):
        context = self.get_context_data(enrollment=enrollment, form=form)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        enrollment = self.get_enrollment()
        return self.render(enrollment, EnrollmentTransferForm(enrollment=enrollment))

    def post(self, request, *args, **kwargs):
        enrollment = self.get_enrollment()
        form = EnrollmentTransferForm(request.POST, enrollment=enrollment)
        if not form.is_valid():
            return self.render(enrollment, form)
        target = form.cleaned_data["course"]
        with transaction.atomic():
            enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
            installments = list(
                Installment.objects.select_for_update().filter(enrollment=enrollment)
            )
            if form.cleaned_data["use_course_fees"]:
                fees = {"enrollment_fee": target.enrollment_fee, "monthly_fee": target.monthly_fee}
            else:
                fees = {
                    "enrollment_fee": enrollment.enrollment_fee,
                    "monthly_fee": enrollment.monthly_fee,
                }
            errors = fee_conflicts(installments, fees)
            if errors:
                for _kind, message in errors:
                    form.add_error(None, message)
                form.add_error(
                    None, "Desmarca «Usar los costos del nuevo curso» para conservar los actuales."
                )
                return self.render(enrollment, form)
            enrollment.course = target
            enrollment.enrollment_fee = fees["enrollment_fee"]
            enrollment.monthly_fee = fees["monthly_fee"]
            enrollment.save()
            sync_initial_installments(enrollment, installments, refresh_due_dates=True)
        messages.success(
            request,
            f"Matrícula trasladada a {target}. Los pagos se conservaron y la deuda se recalculó.",
        )
        message = seats_message(target)
        if message:
            messages.info(request, message)
        return redirect("enrollment-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollment = kwargs["enrollment"]
        installments = list(Installment.objects.filter(enrollment=enrollment, active=True))
        context["paid_total"] = sum(i.paid_amount for i in installments)
        return context


def restore_enrollment(enrollment):
    """Reactiva una matrícula con sus cuotas y los recibos que anuló la baja."""
    enrollment.active = True
    enrollment.deactivated_with_student = False
    enrollment.save(update_fields=["active", "deactivated_with_student"])
    Installment.objects.filter(enrollment=enrollment).update(active=True)
    Payment.objects.filter(
        enrollment=enrollment, status=Payment.Status.VOID, voided_on_deactivation=True
    ).update(status=Payment.Status.CONFIRMED, voided_on_deactivation=False)
    # Las cuotas iniciales vuelven a reflejar los costos vigentes de la matrícula.
    sync_initial_installments(enrollment, list(Installment.objects.filter(enrollment=enrollment)))


class TrashView(CampusScopedMixin, TemplateView):
    # Basta uno de los dos permisos; cada tabla se muestra según el suyo.
    required_permission = None
    template_name = "students/trash.html"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not (
            user.has_perm("core.deactivate_student") or user.has_perm("core.deactivate_enrollment")
        ):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("No tienes permiso para acceder a esta sección.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        user = self.request.user
        context["students"] = (
            Student.objects.filter(campus=campus, active=False).order_by("-pk")[:TRASH_LIMIT]
            if user.has_perm("core.deactivate_student")
            else []
        )
        context["enrollments"] = (
            Enrollment.objects.filter(campus=campus, active=False)
            .select_related("student", "course")
            .order_by("-pk")[:TRASH_LIMIT]
            if user.has_perm("core.deactivate_enrollment")
            else []
        )
        return context


class RestoreStudentView(CampusScopedMixin, View):
    required_permission = "core.deactivate_student"

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk, campus=get_selected_campus(request))
        with transaction.atomic():
            student.active = True
            student.save(update_fields=["active"])
            enrollments = Enrollment.objects.filter(
                student=student, active=False, deactivated_with_student=True
            ).select_related("course")
            restored = 0
            for enrollment in enrollments:
                restore_enrollment(enrollment)
                restored += 1
        messages.success(
            request,
            f"Estudiante {student.full_name} restaurado con {restored} matrícula(s) y sus recibos.",
        )
        return redirect(reverse("trash"))


class RestoreEnrollmentView(CampusScopedMixin, View):
    required_permission = "core.deactivate_enrollment"

    def post(self, request, pk):
        enrollment = get_object_or_404(
            Enrollment.objects.select_related("student", "course"),
            pk=pk,
            campus=get_selected_campus(request),
        )
        if enrollment.student_id and not enrollment.student.active:
            messages.error(
                request,
                f"Primero restaura al estudiante {enrollment.student.full_name}.",
            )
            return redirect(reverse("trash"))
        with transaction.atomic():
            restore_enrollment(enrollment)
        messages.success(request, f"Matrícula restaurada: {enrollment}.")
        message = seats_message(enrollment.course)
        if message:
            messages.info(request, message)
        return redirect(reverse("trash"))
