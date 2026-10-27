from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models.functions import Coalesce
from django.db.models import Count, F, Max, Prefetch, Q, Sum
from django.http import JsonResponse
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
from students.installments import installment_kind
from students.models import Enrollment, Student, mark_student_phone_invalid

from .call_queue import (
    active_claim,
    claim_next,
    close_claim,
    pending_students,
    team_claims,
    user_list,
)
from .forms import CallNoteForm, QuickCallNoteForm, WhatsAppTemplateForm
from .models import (
    EMOJIS,
    PLACEHOLDERS,
    CallClaim,
    CallList,
    CallListMember,
    CallNote,
    WhatsAppSend,
    WhatsAppTemplate,
)

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


def student_message_links(request, campus, student):
    """Enlaces de WhatsApp/SMS con el mensaje de la sede ya armado para un alumno."""
    enrollments = list(
        visible_enrollments(request).filter(student=student).select_related("course")
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
    courses = [
        {
            "course_label": e.course_label,
            "debt": max(billed.get(e.pk, ZERO) - paid.get(e.pk, ZERO), ZERO),
        }
        for e in enrollments
    ]
    total = sum((c["debt"] for c in courses), ZERO)
    promise = (
        CallNote.objects.filter(
            campus=campus,
            student=student,
            response=CallNote.Response.PROMISED_PAYMENT,
            promise_date__isnull=False,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if promise and promise.promise_date < timezone.localdate() and total > 0:
        kind = WhatsAppTemplate.Kind.PROMISE
    elif total > 0:
        kind = WhatsAppTemplate.Kind.DEBT
    else:
        kind = WhatsAppTemplate.Kind.WELCOME
    return build_phone_links(
        WhatsAppTemplate.for_campus(campus)[kind],
        campus,
        student,
        courses,
        total,
        promise.promise_date if promise else None,
    )


def apply_wrong_phone(note, form):
    """Si el resultado es «Teléfono equivocado», inhabilita ese número del alumno (sin borrarlo)."""
    number = form.cleaned_data.get("wrong_phone")
    if note.response != CallNote.Response.WRONG_NUMBER or not number:
        return
    if mark_student_phone_invalid(note.student, number):
        label = note.get_response_display()
        note.note = (
            f"{label}: {number}"
            if not note.note or note.note == label
            else (f"{note.note} ({number})")
        )


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
        enrollments__call_lists__members__user=request.user,
        enrollments__call_lists__active=True,
    ).distinct()


def visible_enrollments(request):
    campus = get_selected_campus(request)
    enrollments = Enrollment.objects.filter(active=True, campus=campus, student__isnull=False)
    if can_view_all_calls(request.user):
        return enrollments
    return enrollments.filter(call_lists__members__user=request.user, call_lists__active=True)


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
                Q(student__full_name__unaccent__wild=q)
                | Q(note__unaccent__wild=q)
                | Q(author__username__wild=q)
                | Q(response__icontains=q.replace(" ", "_"))
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        context["search_query"] = q
        context["pagination_query"] = urlencode({"q": q}) if q else ""
        return context


def course_debts(request, student, all_courses=False):
    """Cursos matriculados del alumno con lo facturado, pagado y adeudado en cada uno."""
    if all_courses:
        enrollments = Enrollment.objects.filter(
            active=True, campus=get_selected_campus(request), student=student
        )
    else:
        enrollments = visible_enrollments(request).filter(student=student)
    enrollments = list(enrollments.select_related("course").order_by("course__name"))
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
    return [
        {
            "enrollment_id": e.pk,
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


CHARGE_KINDS = {"enrollment_fee": ("fee", "Matrícula"), "monthly_fee": ("monthly", "Mensualidad")}


def attach_charges(courses, today=None):
    """Añade a cada curso sus cargos y resume lo pendiente por matrícula, mensualidad y otros."""
    today = today or timezone.localdate()
    charges = defaultdict(list)
    installments = (
        Installment.objects.filter(
            enrollment__in=[c["enrollment_id"] for c in courses], active=True
        )
        .annotate(
            paid=Coalesce(
                Sum(
                    "allocations__amount",
                    filter=Q(allocations__payment__status=Payment.Status.CONFIRMED),
                ),
                ZERO,
            )
        )
        .order_by("due_date", "id")
    )
    for item in installments:
        # Cobros con otro concepto se muestran con su nombre y no se mezclan con la mensualidad.
        kind, label = CHARGE_KINDS.get(installment_kind(item), ("other", item.concept))
        balance = max(item.amount - item.paid, ZERO)
        charges[item.enrollment_id].append(
            {
                "kind": kind,
                "label": label,
                "concept": item.concept,
                "amount": item.amount,
                "paid": min(item.paid, item.amount),
                "balance": balance,
                "due_date": item.due_date,
                "days": (item.due_date - today).days,
                "late": max((today - item.due_date).days, 0) if balance else 0,
            }
        )
    summary = {"fee": ZERO, "monthly": ZERO, "other": ZERO, "oldest_overdue_days": 0}
    for course in courses:
        items = charges.get(course["enrollment_id"], [])
        course["charges"] = items
        for item in items:
            summary[item["kind"]] += item["balance"]
            summary["oldest_overdue_days"] = max(summary["oldest_overdue_days"], item["late"])
    return summary


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
        context["courses"] = course_debts(self.request, student)
        context["total_debt"] = sum((c["debt"] for c in context["courses"]), ZERO)
        return context


class CallNoteCreateView(StudentNotesMixin, TemplateView):
    required_permission = "calls.add_callnote"
    template_name = "calls/note_form.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student"] = self.get_student()
        context["form"] = form or CallNoteForm(student=context["student"])
        return context

    def post(self, request, *args, **kwargs):
        student = self.get_student()
        form = CallNoteForm(request.POST, student=student)
        if form.is_valid():
            note = form.save(commit=False)
            note.campus = get_selected_campus(request)
            note.student = student
            note.author = request.user
            apply_wrong_phone(note, form)
            note.save()
            if close_claim(request.user, student):
                return redirect("calls-queue")
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

    def get_required_permissions(self, request):
        # El gestor trabaja desde la cola; el seguimiento es para quien supervisa o asigna.
        if request.user.has_perm("core.assign_calls"):
            return ("calls.view_callnote", "core.assign_calls")
        return ("calls.view_callnote", "core.view_all_calls")

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
            students = students.filter(Q(full_name__unaccent__wild=q) | Q(phone__wild=q))
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
    """Registro rápido de una llamada desde la cola."""

    required_permission = "calls.add_callnote"
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        student = self.get_student()
        form = QuickCallNoteForm(request.POST, student=student)
        if form.is_valid():
            note = form.save(commit=False)
            note.note = note.note or note.get_response_display()
            note.campus = get_selected_campus(request)
            note.student = student
            note.author = request.user
            apply_wrong_phone(note, form)
            note.save()
            close_claim(request.user, student)
            messages.success(request, f"Llamada a {student.full_name} registrada.")
        else:
            errors = "; ".join(e for errs in form.errors.values() for e in errs)
            messages.error(request, f"No se registró la llamada: {errors}")
        target = request.POST.get("next") or ""
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            target = reverse(
                "calls-assignments" if request.user.has_perm("core.assign_calls") else "calls-queue"
            )
        return redirect(target)


class WhatsAppOpenView(StudentNotesMixin, TemplateView):
    """Lleva a WhatsApp con el mensaje de la sede ya armado; no marca nada como enviado."""

    required_permission = "calls.add_callnote"
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        student = self.get_student()
        links = student_message_links(request, get_selected_campus(request), student)
        if not links:
            messages.error(request, f"{student.full_name} no tiene un teléfono válido.")
            return redirect("calls-queue")
        return redirect(links[0]["url"])


class WhatsAppMarkView(StudentNotesMixin, TemplateView):
    """Casilla «WhatsApp enviado» de hoy: la marca o la quita."""

    required_permission = "calls.add_callnote"
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        student = self.get_student()
        campus = get_selected_campus(request)
        today = timezone.localdate()
        if request.POST.get("enviado") == "1":
            WhatsAppSend.objects.get_or_create(
                student=student, date=today, defaults={"campus": campus, "user": request.user}
            )
        else:
            WhatsAppSend.objects.filter(student=student, date=today, campus=campus).delete()
        return JsonResponse({"ok": True})


class CallQueueMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin):
    required_permission = "calls.add_callnote"

    def get_call_list(self):
        campus = get_selected_campus(self.request)
        return user_list(self.request.user, campus)

    def get_history(self, call_list):
        """Resumen de hoy: cada alumno de la sublista, si se llamó, se está llamando o falta."""
        today = timezone.localdate()
        students = list(
            Student.objects.filter(
                active=True,
                campus=call_list.campus,
                enrollments__active=True,
                enrollments__call_lists=call_list,
            ).distinct()
        )
        calling = {c.student_id: c for c in team_claims(call_list)}
        latest = {}
        for note in CallNote.objects.filter(created_at__date=today, student__in=students).order_by(
            "-created_at"
        ):
            latest.setdefault(note.student_id, note)
        rows = []
        for student in students:
            claim = calling.get(student.pk)
            note = latest.get(student.pk)
            if claim:
                state, order = "Llamando", 0
            elif note:
                state, order = "Llamado", 2
            else:
                state, order = "Sin llamar", 1
            rows.append(
                {
                    "student": student,
                    "state": state,
                    "caller": claim.user.username if claim else None,
                    "note": note,
                    "answered": None
                    if not note
                    else note.response
                    not in (CallNote.Response.NO_ANSWER, CallNote.Response.WRONG_NUMBER),
                    "order": order,
                }
            )
        rows.sort(key=lambda r: (r["order"], r["student"].full_name))
        return rows

    def history_rows(self, call_list):
        """Filas del resumen en formato JSON; el navegador actualiza solo las celdas que cambian."""
        busy = active_claim(self.request.user, call_list) is not None
        sent = set(
            WhatsAppSend.objects.filter(
                campus=call_list.campus, date=timezone.localdate()
            ).values_list("student_id", flat=True)
        )
        rows = []
        for r in self.get_history(call_list):
            note = r["note"]
            response = note.response if note else ""
            retry = (
                r["state"] == "Llamado"
                and not busy
                and bool(r["student"].phone)
                and response in (CallNote.Response.NO_ANSWER, CallNote.Response.WRONG_NUMBER)
            )
            rows.append(
                {
                    "id": r["student"].pk,
                    "name": r["student"].full_name,
                    "url": reverse("calls-notes", args=[r["student"].pk]),
                    "state": r["state"],
                    "caller": r["caller"] or "",
                    "answered": r["answered"],
                    "response": response,
                    "label": note.get_response_display() if note else "",
                    "retry": retry,
                    "whatsapp": r["student"].pk in sent,
                    "can_send": bool(r["student"].phone),
                    "open_url": reverse("calls-whatsapp-open", args=[r["student"].pk]),
                    "mark_url": reverse("calls-whatsapp-mark", args=[r["student"].pk]),
                }
            )
        return rows


class CallQueueView(CallQueueMixin, TemplateView):
    """El usuario pide su siguiente llamada; el equipo de su sublista ve a quién llama."""

    template_name = "calls/queue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        call_list = self.get_call_list()
        context["call_list"] = call_list
        if not call_list:
            return context
        claim = active_claim(self.request.user, call_list)
        context["claim"] = claim
        team = list(team_claims(call_list, self.request.user))
        context["team"] = team
        context["team_ids_json"] = "[" + ",".join(str(c.pk) for c in team) + "]"
        context["pending_count"] = pending_students(call_list).count()
        context["minutes"] = CallClaim.MINUTES
        context["history"] = self.get_history(call_list)
        context["history_rows"] = self.history_rows(call_list)
        context["response_choices"] = CallNote.Response.choices
        if claim:
            student = claim.student
            context["phones"] = [p.strip() for p in student.phone.split(",") if p.strip()]
            context["courses"] = course_debts(self.request, student, all_courses=True)
            context["total_debt"] = sum((c["debt"] for c in context["courses"]), ZERO)
            context["debt_summary"] = attach_charges(context["courses"])
            context["last_note"] = student.call_notes.select_related("author").first()
        return context

    def post(self, request, *args, **kwargs):
        call_list = self.get_call_list()
        if not call_list:
            messages.error(request, "No perteneces a ninguna sublista activa de esta sede.")
            return redirect("calls-queue")
        action = request.POST.get("accion", "")
        if action == "pedir":
            student_id = request.POST.get("alumno", "")
            claim, created = claim_next(
                request.user, call_list, int(student_id) if student_id.isdigit() else None
            )
            if claim is None:
                messages.info(
                    request, "Ese alumno no está disponible o no quedan alumnos por llamar."
                )
            elif created:
                messages.success(
                    request, f"Llamarás a {claim.student.full_name}. Tu equipo ya lo sabe."
                )
        elif action == "liberar":
            claim = active_claim(request.user, call_list)
            if claim:
                close_claim(request.user, claim.student, CallClaim.Status.RELEASED)
                messages.info(request, f"Liberaste a {claim.student.full_name}; vuelve a la cola.")
        return redirect("calls-queue")


class CallQueueStatusView(CallQueueMixin, TemplateView):
    """Estado en vivo del equipo; la página lo pide al recibir un aviso por WebSocket."""

    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        call_list = self.get_call_list()
        if not call_list:
            return JsonResponse({"team": [], "pending": 0})
        return JsonResponse(
            {
                "pending": pending_students(call_list).count(),
                "history_rows": self.history_rows(call_list),
                "team": [
                    {
                        "id": c.pk,
                        "user": c.user.username,
                        "student": c.student.full_name,
                        "since": timezone.localtime(c.started_at).strftime("%H:%M"),
                    }
                    for c in team_claims(call_list, request.user)
                ],
            }
        )


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
            call_list__enrollments__student__call_notes__campus=campus,
            call_list__enrollments__student__call_notes__author=F("user"),
            call_list__enrollments__student__call_notes__created_at__date__gte=start,
            call_list__enrollments__student__call_notes__created_at__date__lte=end,
        )
        live = Q(
            call_list__enrollments__campus=campus,
            call_list__enrollments__active=True,
            call_list__enrollments__student__active=True,
        )
        progress = CallListMember.objects.filter(call_list__campus=campus)
        if not can_view_all_calls(self.request.user):
            progress = progress.filter(user=self.request.user)
        for item in progress.values("user__username").annotate(
            assigned=Count("call_list__enrollments", distinct=True, filter=live),
            called=Count("call_list__enrollments", distinct=True, filter=live & in_range),
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
    """El asignador arma sublistas de matrículas y las entrega a varios usuarios de llamadas."""

    required_permission = "core.assign_calls"
    template_name = "calls/assignments.html"
    per_page = 50

    def get_users(self, only_campus=True):
        campus = get_selected_campus(self.request)
        assigners = users_with_perm("core.assign_calls").values("pk")
        users = users_with_perm("calls.add_callnote").filter(is_superuser=False)
        if only_campus:
            users = users.filter(campuses=campus)
        return users.exclude(pk__in=assigners).distinct().order_by("username")

    def get_lists(self):
        return CallList.objects.filter(campus=get_selected_campus(self.request))

    def get_target(self):
        raw = self.request.GET.get("lista") or self.request.POST.get("lista") or ""
        return self.get_lists().filter(pk=int(raw)).first() if raw.isdigit() else None

    def get_filters(self, params=None):
        params = self.request.GET if params is None else params
        return {
            "q": params.get("q", "").strip(),
            "curso": params.get("curso", "").strip(),
            "horario": params.get("horario", "").strip(),
            "grupo": params.get("grupo", "").strip(),
            "estado": params.get("estado", "").strip(),
            "deuda": params.get("deuda", "") == "1",
            "situacion": (
                params.get("situacion", "")
                if params.get("situacion", "") in ("ya_inicio", "por_iniciar", "incorporacion")
                else ""
            ),
            **{
                key: params.get(key, "").strip()
                for key in (
                    "matricula_desde",
                    "matricula_hasta",
                    "inicio_desde",
                    "inicio_hasta",
                )
                if parse_date(params.get(key, "").strip())
            },
        }

    def get_base_enrollments(self):
        return Enrollment.objects.filter(
            active=True, campus=get_selected_campus(self.request), student__active=True
        )

    def get_enrollments(self, params=None):
        f = self.get_filters(params)
        qs = self.get_base_enrollments().select_related("student", "course")
        if f["q"]:
            qs = qs.filter(student__full_name__unaccent__wild=f["q"])
        for key, lookup in (
            ("matricula_desde", "enrollment_date__gte"),
            ("matricula_hasta", "enrollment_date__lte"),
            ("inicio_desde", "course__start_date__gte"),
            ("inicio_hasta", "course__start_date__lte"),
        ):
            if f.get(key):
                qs = qs.filter(**{lookup: parse_date(f[key])})
        today = timezone.localdate()
        if f["situacion"] == "incorporacion":
            qs = qs.filter(enrollment_date__gt=F("course__start_date"))
        elif f["situacion"] == "ya_inicio":
            qs = qs.filter(
                course__start_date__lte=today, enrollment_date__lte=F("course__start_date")
            )
        elif f["situacion"] == "por_iniciar":
            qs = qs.filter(
                course__start_date__gt=today, enrollment_date__lte=F("course__start_date")
            )
        if f["curso"]:
            qs = qs.filter(course__name=f["curso"])
        if f["horario"]:
            qs = qs.filter(course__schedule=f["horario"])
        if f["grupo"]:
            qs = qs.filter(course__group=f["grupo"])
        if f["estado"] == "sin_asignar":
            qs = qs.filter(call_lists__isnull=True)
        elif f["estado"] == "en_alguna":
            qs = qs.filter(call_lists__isnull=False)
        if f["deuda"]:
            qs = qs.filter(pk__in=pending_enrollments_for_campus(get_selected_campus(self.request)))
        return qs.distinct().order_by("student__full_name", "course__name", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self.get_filters()
        page = Paginator(self.get_enrollments(), self.per_page).get_page(
            self.request.GET.get("page")
        )
        owners = defaultdict(list)
        page_ids = [e.pk for e in page.object_list]
        for link in CallList.enrollments.through.objects.filter(
            enrollment_id__in=page_ids, calllist__campus=get_selected_campus(self.request)
        ).select_related("calllist"):
            owners[link.enrollment_id].append(link.calllist.name)
        base = self.get_base_enrollments().select_related("course")
        courses = base.values_list("course__name", flat=True).distinct().order_by("course__name")
        schedules = (
            base.values_list("course__schedule", flat=True).distinct().order_by("course__schedule")
        )
        groups = base.values_list("course__group", flat=True).distinct().order_by("course__group")
        params = {k: v for k, v in filters.items() if v}
        if filters["deuda"]:
            params["deuda"] = "1"
        busy = {
            m.user_id: m.call_list
            for m in CallListMember.objects.filter(
                call_list__campus=get_selected_campus(self.request)
            ).select_related("call_list")
        }
        in_campus = {u.pk for u in self.get_users()}
        callers = [
            {
                "user": u,
                "other": busy.get(u.pk),
                "no_campus": u.pk not in in_campus,
            }
            for u in self.get_users(only_campus=False)
        ]
        lists = list(
            self.get_lists()
            .annotate(
                enrollment_total=Count(
                    "enrollments", distinct=True, filter=Q(enrollments__active=True)
                ),
            )
            .prefetch_related(
                "members__user",
                Prefetch(
                    "enrollments",
                    queryset=Enrollment.objects.filter(active=True)
                    .select_related("student", "course")
                    .order_by("student__full_name", "pk"),
                    to_attr="active_enrollments",
                ),
            )
        )
        context.update(
            lists=lists,
            callers=callers,
            page_obj=page,
            is_paginated=page.paginator.num_pages > 1,
            rows=[
                {"enrollment": e, "owners": ", ".join(owners.get(e.pk, []))}
                for e in page.object_list
            ],
            filters=filters,
            courses=[c for c in courses if c],
            schedules=[s for s in schedules if s],
            groups=[g for g in groups if g],
            total_results=page.paginator.count,
            search_query=filters["q"],
            pagination_query=urlencode(params),
            all_ids=",".join(str(pk) for pk in self.get_enrollments().values_list("pk", flat=True)),
        )
        return context

    def create_list(self, request):
        """Crea una sublista con nombre, estado, usuarios y las matrículas del filtro."""
        campus = get_selected_campus(request)
        name = " ".join(request.POST.get("nombre", "").split())[:80]
        if not name:
            messages.error(request, "Escribe un nombre para la sublista.")
            return None
        if CallList.objects.filter(campus=campus, name__iexact=name).exists():
            messages.error(request, f"Ya existe una sublista llamada «{name}».")
            return None
        allowed = {u.pk for u in self.get_users()}
        picked = {int(i) for i in request.POST.getlist("usuarios") if i.isdigit()} & allowed
        busy = dict(
            CallListMember.objects.filter(user_id__in=picked, call_list__campus=campus).values_list(
                "user__username", "call_list__name"
            )
        )
        if busy:
            detail = ", ".join(f"{user} (en «{lst}»)" for user, lst in sorted(busy.items()))
            messages.error(
                request,
                f"No se creó la sublista: {detail} ya pertenece a otra sublista de esta sede. "
                "Quítalo de ella primero.",
            )
            return None
        active = request.POST.get("estado_lista", "activa") != "inactiva"
        try:
            with transaction.atomic():
                call_list = CallList.objects.create(
                    campus=campus, name=name, active=active, created_by=request.user
                )
                CallListMember.objects.bulk_create(
                    CallListMember(
                        campus=campus, call_list=call_list, user_id=pk, assigned_by=request.user
                    )
                    for pk in picked
                )
                chosen = {int(i) for i in request.POST.getlist("enrollments") if i.isdigit()}
                valid = (
                    self.get_base_enrollments().filter(pk__in=chosen).values_list("pk", flat=True)
                )
                call_list.enrollments.add(*valid)
        except IntegrityError:
            messages.error(
                request,
                "Otro asignador cambió las sublistas o sus usuarios al mismo tiempo. "
                "Intenta de nuevo.",
            )
            return None
        messages.success(
            request,
            f"Sublista «{call_list.name}» creada con {call_list.enrollments.count()} "
            f"matrícula(s) y {len(picked)} usuario(s).",
        )
        return call_list

    def post(self, request, *args, **kwargs):
        action = request.POST.get("accion", "")
        if action == "crear_lista":
            self.create_list(request)
            return redirect("calls-assignments")
        target = self.get_target()
        if not target:
            messages.error(request, "Selecciona una sublista válida.")
            return redirect("calls-assignments")
        if action == "eliminar_lista":
            name = target.name
            target.delete()
            messages.success(request, f"Sublista «{name}» eliminada; sus usuarios quedaron libres.")
        elif action == "quitar_matricula":
            raw = request.POST.get("matricula", "")
            if raw.isdigit():
                target.enrollments.remove(int(raw))
                messages.success(request, f"Matrícula quitada de «{target.name}».")
        elif action == "quitar_usuario":
            raw = request.POST.get("miembro", "")
            removed, _ = target.members.filter(pk=int(raw) if raw.isdigit() else 0).delete()
            if removed:
                messages.success(request, f"Usuario quitado de «{target.name}»; ya está libre.")
        return redirect("calls-assignments")
