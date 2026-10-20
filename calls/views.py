from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from django.http import QueryDict
from django.db.models import Count, F, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, TemplateView

from core.campus import (
    FeaturePermissionMixin,
    SelectedCampusRequiredMixin,
    get_selected_campus,
    users_with_perm,
)
from core.pagination import paginate_context
from payments.forms import pending_enrollments_for_campus
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Enrollment, Student

from .forms import CallNoteForm, QuickCallNoteForm, WhatsAppTemplateForm
from .models import EMOJIS, PLACEHOLDERS, CallAssignment, CallNote, WhatsAppTemplate

ZERO = Decimal("0.00")


def whatsapp_message(template, campus, student, courses, total, promise_date=None):
    detail = "\n".join(
        f"- {c['course_label']}: S/ {c['debt']:.2f}" for c in courses if c["debt"] > 0
    )
    return template.render(
        alumno=student.full_name,
        sede=campus.name,
        deuda_total=f"{total:.2f}",
        detalle_deuda=detail or "Sin deuda pendiente",
        fecha_promesa=promise_date.strftime("%d/%m/%Y") if promise_date else "",
    )


def build_phone_links(template, campus, student, courses, total, promise_date=None):
    message = whatsapp_message(template, campus, student, courses, total, promise_date)
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
    return user.has_perm("core.view_all_calls")


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
    enrollments = Enrollment.objects.filter(active=True, campus=campus, student__isnull=False)
    if can_view_all_calls(request.user):
        return enrollments
    return enrollments.filter(call_assignments__user=request.user)


class StudentNotesMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    required_permission = "calls.view_callnote"

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
                "course_label": e.course_label,
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
    required_permission = "calls.add_callnote"
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
    required_permission = "core.edit_call_notes"
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
    required_permission = "calls.add_callnote"
    template_name = "calls/template_form.html"

    @property
    def kind(self):
        value = self.request.GET.get("tipo") or self.request.POST.get("tipo") or ""
        return value if value in WhatsAppTemplate.Kind.values else WhatsAppTemplate.Kind.DEBT

    def get_template(self):
        template, _ = WhatsAppTemplate.objects.get_or_create(
            campus=get_selected_campus(self.request),
            kind=self.kind,
            defaults={"body": WhatsAppTemplate.DEFAULT_BODIES[self.kind]},
        )
        return template

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.get_template()
        context["form"] = form or WhatsAppTemplateForm(instance=template)
        context["placeholders"] = PLACEHOLDERS.items()
        context["emojis"] = EMOJIS
        context["kind"] = self.kind
        context["kinds"] = WhatsAppTemplate.Kind.choices
        sample = {
            "alumno": "María Pérez",
            "sede": get_selected_campus(self.request).name,
            "deuda_total": "150.00",
            "detalle_deuda": "- Inglés: S/ 100.00\n- Computación: S/ 50.00",
            "fecha_promesa": "15/10/2026",
        }
        context["sample"] = sample
        context["preview"] = template.render(**sample)
        return context

    def post(self, request, *args, **kwargs):
        form = WhatsAppTemplateForm(request.POST, instance=self.get_template())
        if form.is_valid():
            form.save()
            messages.success(request, "Plantilla de WhatsApp guardada.")
            return redirect(f"{reverse('calls-template')}?tipo={self.kind}")
        return self.render_to_response(self.get_context_data(form=form))


class CallStudentListView(FeaturePermissionMixin, SelectedCampusRequiredMixin, ListView):
    """Alumnos con sus cursos matriculados, deuda por curso y teléfonos para llamar."""

    required_permission = "calls.view_callnote"
    template_name = "calls/student_list.html"
    context_object_name = "rows"
    paginate_by = 50

    ORDERS = {
        "": "Nombre",
        "deuda": "Mayor deuda",
        "vencida": "Más días vencida",
        "sin_contacto": "Más tiempo sin llamar",
    }
    CONTACTS = {
        "": "Todos",
        "nunca": "Sin llamadas",
        "7": "Sin llamar hace 7+ días",
        "15": "Sin llamar hace 15+ días",
        "30": "Sin llamar hace 30+ días",
    }

    @property
    def only_debt(self):
        return self.request.GET.get("deuda") == "1"

    @property
    def order(self):
        value = self.request.GET.get("orden", "")
        return value if value in self.ORDERS else ""

    @property
    def contact(self):
        value = self.request.GET.get("contacto", "")
        return value if value in self.CONTACTS else ""

    PROMISES = {
        "": "Promesas: todas",
        "vencida": "Promesas incumplidas",
        "hoy": "Llamar hoy (vencen hoy o mañana)",
    }

    @property
    def promise_filter(self):
        value = self.request.GET.get("promesa", "")
        return value if value in ("vencida", "hoy") else ""

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
                    "enrollment_id": enrollment.pk,
                    "course": enrollment.course,
                    "course_label": enrollment.course_label,
                    "enrollment_fee": enrollment.enrollment_fee,
                    "monthly_fee": enrollment.monthly_fee,
                    "total": billed.get(enrollment.pk, ZERO),
                    "debt": max(debt, ZERO),
                    "receipts": receipts[enrollment.pk],
                }
            )
        templates = WhatsAppTemplate.for_campus(campus)
        notes_count = dict(
            CallNote.objects.filter(campus=campus, student__in=students)
            .values_list("student")
            .annotate(n=Count("id"))
        )
        last_call = dict(
            CallNote.objects.filter(campus=campus, student__in=students)
            .values_list("student")
            .annotate(last=Max("created_at"))
        )
        promises = {}
        for note in CallNote.objects.filter(
            campus=campus,
            student__in=students,
            response=CallNote.Response.PROMISED_PAYMENT,
            promise_date__isnull=False,
        ).order_by("created_at", "id"):
            promises[note.student_id] = note
        today = timezone.localdate()
        oldest_due = {}
        unpaid = (
            Installment.objects.filter(enrollment__in=ids, active=True, due_date__lt=today)
            .annotate(
                paid=Coalesce(
                    Sum(
                        "allocations__amount",
                        filter=Q(allocations__payment__status=Payment.Status.CONFIRMED),
                    ),
                    ZERO,
                )
            )
            .filter(amount__gt=F("paid"))
            .values_list("enrollment__student_id", "due_date")
        )
        for student_id, due in unpaid:
            if student_id not in oldest_due or due < oldest_due[student_id]:
                oldest_due[student_id] = due
        contact = self.contact
        rows = []
        for student in students:
            courses = by_student[student.pk]
            total = sum((c["debt"] for c in courses), ZERO)
            if self.only_debt and total <= 0:
                continue
            last = last_call.get(student.pk)
            days_since_call = (today - timezone.localtime(last).date()).days if last else None
            promise = promises.get(student.pk)
            promise_broken = bool(promise and promise.promise_date < today and total > 0)
            promise_due_soon = bool(
                promise and today <= promise.promise_date <= today + timedelta(days=1) and total > 0
            )
            if self.promise_filter == "vencida" and not promise_broken:
                continue
            if self.promise_filter == "hoy" and not promise_due_soon:
                continue
            if contact == "nunca" and last:
                continue
            if contact.isdigit() and last and days_since_call < int(contact):
                continue
            if promise_broken:
                kind = WhatsAppTemplate.Kind.PROMISE
            elif total > 0:
                kind = WhatsAppTemplate.Kind.DEBT
            else:
                kind = WhatsAppTemplate.Kind.WELCOME
            due = oldest_due.get(student.pk)
            rows.append(
                {
                    "student": student,
                    "courses": courses,
                    "total_debt": total,
                    "notes_count": notes_count.get(student.pk, 0),
                    "phones": build_phone_links(
                        templates[kind],
                        campus,
                        student,
                        courses,
                        total,
                        promise.promise_date if promise else None,
                    ),
                    "message_kind": WhatsAppTemplate.Kind(kind).label,
                    "last_call": last,
                    "days_since_call": days_since_call,
                    "promise": promise,
                    "promise_broken": promise_broken,
                    "promise_due_soon": promise_due_soon,
                    "overdue_days": (today - due).days if due and total > 0 else 0,
                    "pay_enrollment_id": max(courses, key=lambda c: c["debt"])["enrollment_id"]
                    if total > 0
                    else None,
                }
            )
        order = self.order
        if order == "deuda":
            rows.sort(key=lambda r: -r["total_debt"])
        elif order == "vencida":
            rows.sort(key=lambda r: -r["overdue_days"])
        elif order == "sin_contacto":
            rows.sort(
                key=lambda r: (
                    r["days_since_call"] is not None,
                    -(r["days_since_call"] or 0),
                )
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
        for key, value in (
            ("orden", self.order),
            ("contacto", self.contact),
            ("promesa", self.promise_filter),
        ):
            if value:
                params[key] = value
        context["search_query"] = q
        context["only_debt"] = self.only_debt
        context["order"] = self.order
        context["contact"] = self.contact
        context["promise_filter"] = self.promise_filter
        context["orders"] = self.ORDERS.items()
        context["contacts"] = self.CONTACTS.items()
        context["promises"] = self.PROMISES.items()
        context["response_choices"] = CallNote.Response.choices
        context["pagination_query"] = urlencode(params)
        return context


class CallQuickNoteView(StudentNotesMixin, TemplateView):
    """Registro rápido de una llamada desde la lista de alumnos."""

    required_permission = "calls.add_callnote"
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        student = self.get_student()
        form = QuickCallNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.note = note.note or note.get_response_display()
            note.campus = get_selected_campus(request)
            note.student = student
            note.author = request.user
            note.save()
            messages.success(request, f"Llamada a {student.full_name} registrada.")
        else:
            errors = "; ".join(e for errs in form.errors.values() for e in errs)
            messages.error(request, f"No se registró la llamada: {errors}")
        target = request.POST.get("next") or ""
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            target = reverse("calls-students")
        return redirect(target)


class CallReportView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Resumen de llamadas por usuario en un rango de fechas, limitado a la sede seleccionada."""

    required_permission = "core.view_call_reports"
    template_name = "calls/report.html"

    def get_dates(self):
        today = timezone.localdate()
        start = parse_date(self.request.GET.get("desde", "")) or today.replace(day=1)
        end = parse_date(self.request.GET.get("hasta", "")) or today
        return (end, start) if start > end else (start, end)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = self.get_dates()
        notes = CallNote.objects.filter(
            campus=get_selected_campus(self.request),
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        if not can_view_all_calls(self.request.user):
            notes = notes.filter(author=self.request.user)
        campus = get_selected_campus(self.request)
        by_response = {key: Count("pk", filter=Q(response=key)) for key in CallNote.Response.values}
        columns = {
            "total": Count("pk"),
            "students": Count("student", distinct=True),
            "will": by_response[CallNote.Response.WILL_ATTEND],
            "wont": by_response[CallNote.Response.WONT_ATTEND],
            "no_answer": by_response[CallNote.Response.NO_ANSWER],
            "promised": by_response[CallNote.Response.PROMISED_PAYMENT],
            "other": by_response[CallNote.Response.OTHER],
        }
        rows = {
            row["author__username"]: row
            for row in notes.values("author__username").annotate(**columns)
        }
        in_range = Q(
            enrollment__student__call_notes__campus=campus,
            enrollment__student__call_notes__author=F("user"),
            enrollment__student__call_notes__created_at__date__gte=start,
            enrollment__student__call_notes__created_at__date__lte=end,
        )
        progress = CallAssignment.objects.filter(
            enrollment__campus=campus,
            enrollment__active=True,
            enrollment__student__active=True,
        )
        if not can_view_all_calls(self.request.user):
            progress = progress.filter(user=self.request.user)
        for item in progress.values("user__username").annotate(
            assigned=Count("enrollment", distinct=True),
            called=Count("enrollment", distinct=True, filter=in_range),
        ):
            row = rows.setdefault(
                item["user__username"],
                {"author__username": item["user__username"], **dict.fromkeys(columns, 0)},
            )
            row["assigned"] = item["assigned"]
            row["called"] = item["called"]
            row["pending"] = item["assigned"] - item["called"]
            row["progress"] = (
                round(100 * item["called"] / item["assigned"]) if item["assigned"] else 0
            )
        ordered = sorted(rows.values(), key=lambda r: (-r["total"], r["author__username"]))
        context.update(
            start=start,
            end=end,
            rows=ordered,
            totals=notes.aggregate(**columns),
            scope_all=can_view_all_calls(self.request.user),
        )
        return context


class CallAssignmentView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Permite elegir qué matrículas ve cada usuario con acceso a llamadas."""

    required_permission = "core.assign_calls"
    template_name = "calls/assignments.html"
    per_page = 50

    def get_users(self):
        campus = get_selected_campus(self.request)
        assigners = users_with_perm("core.assign_calls").values("pk")
        return (
            users_with_perm("calls.add_callnote")
            .filter(is_superuser=False, campuses=campus)
            .exclude(pk__in=assigners)
            .order_by("username")
        )

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
        assigned_list = (
            CallAssignment.objects.filter(
                user=target, enrollment__campus=get_selected_campus(self.request)
            )
            .filter(enrollment__active=True)
            .select_related("enrollment__student", "enrollment__course")
            .order_by("enrollment__student__full_name", "enrollment_id")
            if target
            else []
        )
        loads = dict(
            CallAssignment.objects.filter(
                enrollment__campus=get_selected_campus(self.request), enrollment__active=True
            )
            .values_list("user_id")
            .annotate(n=Count("enrollment", distinct=True))
        )
        context.update(
            users=self.get_users(),
            target=target,
            assigned_list=assigned_list,
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
            unassigned_count=self.get_base_enrollments()
            .filter(call_assignments__isnull=True)
            .count(),
            source_users=[
                (u, loads.get(u.pk, 0)) for u in self.get_users() if not target or u.pk != target.pk
            ],
        )
        return context

    def bulk_move(self, request):
        campus = get_selected_campus(request)
        users = self.get_users()
        source = (
            users.filter(pk=int(request.POST["origen"])).first()
            if request.POST.get("origen", "").isdigit()
            else None
        )
        target = self.get_target()
        if not source or not target or source.pk == target.pk:
            messages.error(request, "Elige un usuario de origen y otro de destino distintos.")
            return
        moving = CallAssignment.objects.filter(user=source, enrollment__campus=campus)
        already = CallAssignment.objects.filter(user=target).values("enrollment_id")
        moved = moving.exclude(enrollment_id__in=already).update(
            user=target, assigned_by=request.user
        )
        moving.delete()
        messages.success(
            request, f"{moved} asignaciones pasaron de {source.username} a {target.username}."
        )

    def bulk_split(self, request):
        picked = {int(i) for i in request.POST.getlist("reparto") if i.isdigit()}
        users = list(self.get_users().filter(pk__in=picked).order_by("username"))
        if not users:
            messages.error(request, "Selecciona al menos un usuario para repartir.")
            return
        enrollments = list(
            self.get_base_enrollments()
            .filter(call_assignments__isnull=True)
            .order_by("student__full_name", "pk")
            .values_list("pk", flat=True)
        )
        CallAssignment.objects.bulk_create(
            CallAssignment(user=users[i % len(users)], enrollment_id=pk, assigned_by=request.user)
            for i, pk in enumerate(enrollments)
        )
        messages.success(
            request,
            f"{len(enrollments)} matrículas sin asignar repartidas entre {len(users)} usuarios.",
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get("accion", "")
        if action in {"reasignar", "repartir"}:
            (self.bulk_move if action == "reasignar" else self.bulk_split)(request)
            return redirect(
                request.path
                + (
                    f"?usuario={request.POST['usuario']}"
                    if request.POST.get("usuario", "").isdigit()
                    else ""
                )
            )
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
        keep = QueryDict(request.POST.get("volver", "")).copy()
        keep.pop("page", None)
        keep["usuario"] = str(target.pk)
        return redirect(f"{request.path}?{keep.urlencode()}")
