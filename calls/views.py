from collections import defaultdict
from decimal import Decimal
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, TemplateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Enrollment, Student

from .forms import CallNoteForm, WhatsAppTemplateForm
from .models import EMOJIS, PLACEHOLDERS, CallNote, WhatsAppTemplate

ZERO = Decimal("0.00")


def whatsapp_message(template, campus, student, courses, total):
    detail = "\n".join(
        f"- {c['course'].name}: S/ {c['debt']:.2f}" for c in courses if c["debt"] > 0
    )
    return template.render(
        alumno=student.full_name,
        sede=campus.name,
        deuda_total=f"{total:.2f}",
        detalle_deuda=detail or "Sin deuda pendiente",
    )


def build_phone_links(template, campus, student, courses, total):
    message = whatsapp_message(template, campus, student, courses, total)
    message = quote(message.replace("\r\n", "\n"), safe="")
    phones = [p.strip() for p in student.phone.split(",") if p.strip()]
    return [
        {
            "number": p,
            "url": f"https://api.whatsapp.com/send?phone=51{p}&text={message}",
        }
        for p in phones
    ]


class StudentNotesMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    permission_field = "can_manage_calls"

    def get_student(self):
        return get_object_or_404(
            Student, pk=self.kwargs["student_id"], campus=get_selected_campus(self.request)
        )


class CallNoteAllListView(StudentNotesMixin, ListView):
    """Historial de llamadas de llamadas de la sede seleccionada."""

    template_name = "calls/note_all.html"
    context_object_name = "notes"
    paginate_by = 50

    def get_queryset(self):
        qs = CallNote.objects.filter(campus=get_selected_campus(self.request)).select_related(
            "student", "author"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(student__full_name__unaccent__icontains=q)
                | Q(note__unaccent__icontains=q)
                | Q(author__username__icontains=q)
                | Q(response__icontains=q.replace(" ", "_"))
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        context["search_query"] = q
        context["pagination_query"] = urlencode({"q": q}) if q else ""
        return context


class CallNoteListView(StudentNotesMixin, TemplateView):
    template_name = "calls/note_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.get_student()
        context["student"] = student
        context["notes"] = CallNote.objects.filter(
            student=student, campus=get_selected_campus(self.request)
        ).select_related("author")
        return context


class CallNoteCreateView(StudentNotesMixin, TemplateView):
    template_name = "calls/note_form.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student"] = self.get_student()
        context["form"] = form or CallNoteForm()
        return context

    def post(self, request, *args, **kwargs):
        student = self.get_student()
        form = CallNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.campus = get_selected_campus(request)
            note.student = student
            note.author = request.user
            note.save()
            messages.success(request, "Llamada registrada en el historial.")
            return redirect("calls-notes", student_id=student.pk)
        return self.render_to_response(self.get_context_data(form=form))


class CallNoteMutationMixin(StudentNotesMixin):
    """Edición y eliminación de un registro de la sede seleccionada."""

    def get_note(self):
        return get_object_or_404(
            CallNote.objects.select_related("student"),
            pk=self.kwargs["pk"],
            campus=get_selected_campus(self.request),
        )

    def get_return_url(self, note):
        target = self.request.POST.get("next") or self.request.GET.get("next") or ""
        if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return target
        return reverse("calls-notes", args=[note.student_id])


class CallNoteUpdateView(CallNoteMutationMixin, TemplateView):
    template_name = "calls/note_form.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        note = self.get_note()
        context["student"] = note.student
        context["note"] = note
        context["form"] = form or CallNoteForm(instance=note)
        context["next"] = self.request.GET.get("next", "")
        return context

    def post(self, request, *args, **kwargs):
        note = self.get_note()
        form = CallNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, "Registro de llamada actualizado.")
            return redirect(self.get_return_url(note))
        return self.render_to_response(self.get_context_data(form=form))


class CallNoteDeleteView(CallNoteMutationMixin, TemplateView):
    template_name = "calls/note_confirm_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        note = self.get_note()
        context["note"] = note
        context["student"] = note.student
        context["next"] = self.request.GET.get("next", "")
        return context

    def post(self, request, *args, **kwargs):
        note = self.get_note()
        url = self.get_return_url(note)
        note.delete()
        messages.success(request, "Registro de llamada eliminado.")
        return redirect(url)


class WhatsAppTemplateView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    permission_field = "can_manage_calls"
    template_name = "calls/template_form.html"

    def get_template(self):
        template, _ = WhatsAppTemplate.objects.get_or_create(
            campus=get_selected_campus(self.request)
        )
        return template

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.get_template()
        context["form"] = form or WhatsAppTemplateForm(instance=template)
        context["placeholders"] = PLACEHOLDERS.items()
        context["emojis"] = EMOJIS
        sample = {
            "alumno": "María Pérez",
            "sede": get_selected_campus(self.request).name,
            "deuda_total": "150.00",
            "detalle_deuda": "- Inglés: S/ 100.00\n- Computación: S/ 50.00",
        }
        context["sample"] = sample
        context["preview"] = template.render(**sample)
        return context

    def post(self, request, *args, **kwargs):
        form = WhatsAppTemplateForm(request.POST, instance=self.get_template())
        if form.is_valid():
            form.save()
            messages.success(request, "Plantilla de WhatsApp guardada.")
            return redirect("calls-template")
        return self.render_to_response(self.get_context_data(form=form))


class CallStudentListView(FeaturePermissionMixin, SelectedCampusRequiredMixin, ListView):
    """Alumnos con sus cursos matriculados, deuda por curso y teléfonos para llamar."""

    permission_field = "can_manage_calls"
    template_name = "calls/student_list.html"
    context_object_name = "rows"
    paginate_by = 50

    @property
    def only_debt(self):
        return self.request.GET.get("deuda") == "1"

    def get_queryset(self):
        campus = get_selected_campus(self.request)
        students = Student.objects.filter(
            campus=campus, active=True, enrollments__active=True, enrollments__campus=campus
        ).distinct()
        q = self.request.GET.get("q", "").strip()
        if q:
            students = students.filter(Q(full_name__unaccent__icontains=q) | Q(phone__icontains=q))
        students = list(students.order_by("full_name"))

        enrollments = list(
            Enrollment.objects.filter(student__in=students, active=True, campus=campus)
            .select_related("course")
            .order_by("course__name")
        )
        ids = [e.pk for e in enrollments]
        billed = dict(
            Installment.objects.filter(enrollment__in=ids, active=True)
            .values_list("enrollment")
            .annotate(total=Sum("amount"))
        )
        paid = dict(
            PaymentAllocation.objects.filter(
                installment__enrollment__in=ids,
                installment__active=True,
                payment__status=Payment.Status.CONFIRMED,
            )
            .values_list("installment__enrollment")
            .annotate(total=Sum("amount"))
        )
        by_student = defaultdict(list)
        receipts = defaultdict(list)
        for payment in Payment.objects.filter(
            enrollment__in=ids, status=Payment.Status.CONFIRMED
        ).order_by("created_at"):
            receipts[payment.enrollment_id].append(payment)
        for enrollment in enrollments:
            debt = billed.get(enrollment.pk, ZERO) - paid.get(enrollment.pk, ZERO)
            by_student[enrollment.student_id].append(
                {
                    "course": enrollment.course,
                    "debt": max(debt, ZERO),
                    "receipts": receipts[enrollment.pk],
                }
            )
        template, _ = WhatsAppTemplate.objects.get_or_create(campus=campus)
        notes_count = dict(
            CallNote.objects.filter(campus=campus, student__in=students)
            .values_list("student")
            .annotate(n=Count("id"))
        )
        rows = []
        for student in students:
            courses = by_student[student.pk]
            total = sum((c["debt"] for c in courses), ZERO)
            if self.only_debt and total <= 0:
                continue
            rows.append(
                {
                    "student": student,
                    "courses": courses,
                    "total_debt": total,
                    "notes_count": notes_count.get(student.pk, 0),
                    "phones": build_phone_links(template, campus, student, courses, total),
                }
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        params = {}
        if q:
            params["q"] = q
        if self.only_debt:
            params["deuda"] = "1"
        context["search_query"] = q
        context["only_debt"] = self.only_debt
        context["pagination_query"] = urlencode(params)
        return context
