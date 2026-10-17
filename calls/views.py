from collections import defaultdict
from decimal import Decimal
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, TemplateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import User
from core.pagination import paginate_context
from payments.forms import pending_enrollments_for_campus
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Enrollment, Student

from .forms import CallNoteForm, WhatsAppTemplateForm
from .models import EMOJIS, PLACEHOLDERS, CallAssignment, CallNote, WhatsAppTemplate

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
            "sms_url": f"sms:+51{p}?&body={message}",
            "tel_url": f"tel:+51{p}",
        }
        for p in phones
    ]


def can_view_all_calls(user):
    return user.is_superuser or user.can_assign_calls


def visible_students(request):
    """Alumnos de la sede cuyas matrículas puede gestionar el usuario en llamadas."""
    campus = get_selected_campus(request)
    students = Student.objects.filter(campus=campus)
    if can_view_all_calls(request.user):
        return students
    return students.filter(
        enrollments__active=True,
        enrollments__campus=campus,
        enrollments__call_assignments__user=request.user,
    ).distinct()


def visible_enrollments(request):
    campus = get_selected_campus(request)
    enrollments = Enrollment.objects.filter(active=True, campus=campus)
    if can_view_all_calls(request.user):
        return enrollments
    return enrollments.filter(call_assignments__user=request.user)


class StudentNotesMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    permission_field = "can_manage_calls"

    def get_student(self):
        return get_object_or_404(visible_students(self.request), pk=self.kwargs["student_id"])


class CallNoteAllListView(StudentNotesMixin, ListView):
    """Historial de llamadas de la sede; quien no asigna solo ve el de sus alumnos."""

    template_name = "calls/note_all.html"
    context_object_name = "notes"
    paginate_by = 50

    def get_queryset(self):
        qs = CallNote.objects.filter(campus=get_selected_campus(self.request)).select_related(
            "student", "author"
        )
        if not can_view_all_calls(self.request.user):
            qs = qs.filter(student__in=visible_students(self.request))
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
        campus = get_selected_campus(self.request)
        context["student"] = student
        notes = CallNote.objects.filter(student=student, campus=campus).select_related("author")
        context.update(paginate_context(self.request, notes, 25))
        context["notes"] = context["page_obj"]
        enrollments = list(
            visible_enrollments(self.request)
            .filter(student=student)
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
        context["courses"] = [
            {
                "course": e.course,
                "enrollment_fee": e.enrollment_fee,
                "monthly_fee": e.monthly_fee,
                "total": billed.get(e.pk, ZERO),
                "paid": paid.get(e.pk, ZERO),
                "debt": max(billed.get(e.pk, ZERO) - paid.get(e.pk, ZERO), ZERO),
            }
            for e in enrollments
        ]
        context["total_debt"] = sum((c["debt"] for c in context["courses"]), ZERO)
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
    permission_field = "can_edit_call_notes"
    """Edición y eliminación de un registro de la sede seleccionada."""

    def get_note(self):
        return get_object_or_404(
            CallNote.objects.select_related("student").filter(
                student__in=visible_students(self.request)
            ),
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
        visible = visible_enrollments(self.request)
        students = Student.objects.filter(
            campus=campus, active=True, enrollments__in=visible
        ).distinct()
        q = self.request.GET.get("q", "").strip()
        if q:
            students = students.filter(Q(full_name__unaccent__icontains=q) | Q(phone__icontains=q))
        students = list(students.order_by("full_name"))

        enrollments = list(
            visible.filter(student__in=students).select_related("course").order_by("course__name")
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
                    "enrollment_fee": enrollment.enrollment_fee,
                    "monthly_fee": enrollment.monthly_fee,
                    "total": billed.get(enrollment.pk, ZERO),
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


class CallAssignmentView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Permite elegir qué matrículas ve cada usuario con acceso a llamadas."""

    permission_field = "can_assign_calls"
    template_name = "calls/assignments.html"
    per_page = 50

    def get_users(self):
        campus = get_selected_campus(self.request)
        return User.objects.filter(
            is_active=True,
            is_superuser=False,
            can_manage_calls=True,
            can_assign_calls=False,
            campuses=campus,
        ).order_by("username")

    def get_target(self):
        raw = self.request.GET.get("usuario") or self.request.POST.get("usuario") or ""
        return self.get_users().filter(pk=int(raw)).first() if raw.isdigit() else None

    def get_filters(self):
        params = self.request.GET
        return {
            "q": params.get("q", "").strip(),
            "curso": params.get("curso", "").strip(),
            "horario": params.get("horario", "").strip(),
            "grupo": params.get("grupo", "").strip(),
            "estado": params.get("estado", "").strip(),
            "deuda": params.get("deuda", "") == "1",
        }

    def get_base_enrollments(self):
        return Enrollment.objects.filter(
            active=True, campus=get_selected_campus(self.request), student__active=True
        )

    def get_enrollments(self):
        f = self.get_filters()
        target = self.get_target()
        qs = self.get_base_enrollments().select_related("student", "course")
        if f["q"]:
            qs = qs.filter(
                Q(student__full_name__unaccent__icontains=f["q"])
                | Q(course__name__unaccent__icontains=f["q"])
            )
        if f["curso"]:
            qs = qs.filter(course__name=f["curso"])
        if f["horario"]:
            qs = qs.filter(course__schedule=f["horario"])
        if f["grupo"]:
            qs = qs.filter(course__group=f["grupo"])
        if f["estado"] == "sin_asignar":
            qs = qs.filter(call_assignments__isnull=True)
        elif f["estado"] == "asignadas" and target:
            qs = qs.filter(call_assignments__user=target)
        elif f["estado"] == "no_asignadas" and target:
            qs = qs.exclude(call_assignments__user=target)
        elif f["estado"] == "otros" and target:
            qs = qs.filter(call_assignments__isnull=False).exclude(call_assignments__user=target)
        if f["deuda"]:
            qs = qs.filter(pk__in=pending_enrollments_for_campus(get_selected_campus(self.request)))
        return qs.distinct().order_by("student__full_name", "course__name", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target = self.get_target()
        filters = self.get_filters()
        page = Paginator(self.get_enrollments(), self.per_page).get_page(
            self.request.GET.get("page")
        )
        assigned = set()
        owners = defaultdict(list)
        page_ids = [e.pk for e in page.object_list]
        for assignment in CallAssignment.objects.filter(enrollment__in=page_ids).select_related(
            "user"
        ):
            owners[assignment.enrollment_id].append(assignment.user.username)
            if target and assignment.user_id == target.pk:
                assigned.add(assignment.enrollment_id)
        base = self.get_base_enrollments().select_related("course")
        courses = base.values_list("course__name", flat=True).distinct().order_by("course__name")
        schedules = (
            base.values_list("course__schedule", flat=True).distinct().order_by("course__schedule")
        )
        groups = base.values_list("course__group", flat=True).distinct().order_by("course__group")
        params = {k: v for k, v in filters.items() if v}
        if filters["deuda"]:
            params["deuda"] = "1"
        if target:
            params["usuario"] = target.pk
        context.update(
            users=self.get_users(),
            target=target,
            page_obj=page,
            is_paginated=page.paginator.num_pages > 1,
            rows=[
                {
                    "enrollment": e,
                    "assigned": e.pk in assigned,
                    "owners": ", ".join(owners.get(e.pk, [])),
                }
                for e in page.object_list
            ],
            filters=filters,
            courses=[c for c in courses if c],
            schedules=[s for s in schedules if s],
            groups=[g for g in groups if g],
            total_results=page.paginator.count,
            search_query=filters["q"],
            pagination_query=urlencode(params),
        )
        return context

    def post(self, request, *args, **kwargs):
        target = self.get_target()
        if not target:
            messages.error(request, "Selecciona un usuario válido.")
            return redirect("calls-assignments")
        campus = get_selected_campus(request)
        shown = {int(i) for i in request.POST.getlist("shown") if i.isdigit()}
        chosen = {int(i) for i in request.POST.getlist("enrollments") if i.isdigit()} & shown
        valid = set(
            Enrollment.objects.filter(pk__in=shown, campus=campus, active=True).values_list(
                "pk", flat=True
            )
        )
        chosen &= valid
        # Solo se modifican las matrículas visibles en la página enviada.
        CallAssignment.objects.filter(user=target, enrollment__in=valid - chosen).delete()
        existing = set(
            CallAssignment.objects.filter(user=target, enrollment__in=chosen).values_list(
                "enrollment_id", flat=True
            )
        )
        CallAssignment.objects.bulk_create(
            CallAssignment(user=target, enrollment_id=pk, assigned_by=request.user)
            for pk in chosen - existing
        )
        messages.success(request, f"Asignaciones de {target.username} actualizadas.")
        return redirect(f"{request.path}?{request.GET.urlencode() or 'usuario=' + str(target.pk)}")
