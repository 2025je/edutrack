from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, DecimalField, F, OuterRef, Prefetch, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from itertools import groupby
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from io import BytesIO
from core.campus import SelectedCampusRequiredMixin, FeaturePermissionMixin, get_selected_campus
from .models import Student, Enrollment, Course
from .forms import StudentForm, EnrollmentForm


class CampusScopedMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin, LoginRequiredMixin):
    permission_field = "can_manage_students"
    def campus_queryset(self, qs, field="campus"):
        campus = get_selected_campus(self.request)
        return qs.filter(**{field: campus})


class StudentListView(CampusScopedMixin, ListView):
    model = Student
    template_name = "students/student_list.html"
    context_object_name = "students"
    paginate_by = 25

    def get_queryset(self):
        qs = self.campus_queryset(Student.objects.select_related("campus"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(document_number__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payable_student_ids"] = set()
        if self.request.user.is_superuser or self.request.user.can_register_payments:
            from payments.forms import pending_enrollments_for_campus
            context["payable_student_ids"] = set(
                pending_enrollments_for_campus(get_selected_campus(self.request))
                .values_list("student_id", flat=True)
            )
        return context


class StudentCreateView(CampusScopedMixin, CreateView):
    model = Student
    form_class = StudentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("student-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.campus = get_selected_campus(self.request)
        response = super().form_valid(form)
        messages.success(self.request, "Estudiante registrado correctamente.")
        return response


class StudentUpdateView(CampusScopedMixin, UpdateView):
    model = Student
    form_class = StudentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("student-list")

    def get_queryset(self):
        return self.campus_queryset(Student.objects.all())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.campus = get_selected_campus(self.request)
        response = super().form_valid(form)
        messages.success(self.request, "Estudiante actualizado correctamente.")
        return response


class StudentDeleteView(CampusScopedMixin, DeleteView):
    model = Student
    template_name = "students/student_confirm_delete.html"
    success_url = reverse_lazy("student-list")

    def get_queryset(self):
        return self.campus_queryset(Student.objects.all())

    def post(self, request, *args, **kwargs):
        student = self.get_object()
        self.object = student
        from payments.models import Installment, Payment
        with transaction.atomic():
            student.active = False
            student.save(update_fields=["active"])
            Enrollment.objects.filter(student=student).update(active=False)
            Installment.objects.filter(enrollment__student=student).update(active=False)
            Payment.objects.filter(
                enrollment__student=student,
                status=Payment.Status.CONFIRMED,
            ).update(status=Payment.Status.VOID)
        messages.success(self.request, "Estudiante dado de baja; se conservaron sus matrículas y recibos, y los recibos confirmados se anularon.")
        return redirect(self.get_success_url())


class EnrollmentListView(CampusScopedMixin, ListView):
    model = Enrollment
    template_name = "students/enrollment_list.html"
    context_object_name = "enrollments"
    paginate_by = 25
    sortable_fields = {
        "row_number": "enrollment_date",
        "student": "student__full_name",
        "course": "course__name",
        "record_code": "record_code",
        "promoter": "promoter__name",
        "enrollment_date": "enrollment_date",
        "start_date": "course__start_date",
        "enrollment_fee": "enrollment_fee",
        "monthly_fee": "monthly_fee",
        "total_enrollment_cost": "total_enrollment_cost",
        "total_paid": "total_paid",
        "total_debt": "total_debt",
        "active": "active",
    }

    def get_queryset(self):
        from decimal import Decimal
        from payments.models import Installment, Payment, PaymentAllocation

        money_field = DecimalField(max_digits=12, decimal_places=2)
        confirmed_allocations = (
            PaymentAllocation.objects.filter(
                installment_id=OuterRef("pk"),
                payment__status=Payment.Status.CONFIRMED,
            )
            .values("installment_id")
            .annotate(total=Sum("amount"))
            .values("total")[:1]
        )
        installments = Installment.objects.annotate(
            paid_total=Coalesce(
                Subquery(confirmed_allocations, output_field=money_field),
                Value(Decimal("0.00"), output_field=money_field),
                output_field=money_field,
            )
        ).annotate(debt_balance=F("amount") - F("paid_total"))
        paid_totals = (
            installments.filter(enrollment_id=OuterRef("pk"))
            .order_by()
            .values("enrollment_id")
            .annotate(total=Sum("paid_total"))
            .values("total")[:1]
        )
        debt_totals = (
            installments.filter(enrollment_id=OuterRef("pk"))
            .order_by()
            .values("enrollment_id")
            .annotate(
                total=Sum(
                    Case(
                        When(debt_balance__gt=0, then=F("debt_balance")),
                        default=Value(Decimal("0.00"), output_field=money_field),
                        output_field=money_field,
                    )
                )
            )
            .values("total")[:1]
        )
        qs = self.campus_queryset(
            Enrollment.objects.select_related("campus", "student", "course")
            .annotate(
                total_enrollment_cost=F("enrollment_fee") + F("monthly_fee"),
                total_paid=Coalesce(
                    Subquery(paid_totals, output_field=money_field),
                    Value(Decimal("0.00"), output_field=money_field),
                    output_field=money_field,
                ),
                total_debt=Coalesce(
                    Subquery(debt_totals, output_field=money_field),
                    Value(Decimal("0.00"), output_field=money_field),
                    output_field=money_field,
                ),
            )
            .prefetch_related(
                Prefetch("installments", queryset=installments),
                Prefetch("payments", queryset=Payment.objects.order_by("created_at", "pk")),
                "promoter",
            )
        )
        filters = {
            "student__full_name__icontains": self.request.GET.get("student", "").strip(),
            "course__name__icontains": self.request.GET.get("course", "").strip(),
            "record_code__icontains": self.request.GET.get("record_code", "").strip(),
            "promoter__name__icontains": self.request.GET.get("promoter", "").strip(),
        }
        for field, value in filters.items():
            if value:
                qs = qs.filter(**{field: value})
        for parameter, field in (
            ("course_id", "course_id"),
            ("promoter_id", "promoter__pk"),
            ("student_id", "student_id"),
        ):
            value = self.request.GET.get(parameter, "").strip()
            if value:
                try:
                    qs = qs.filter(**{field: int(value)})
                except ValueError:
                    qs = qs.none()
        enrollment_date = self.request.GET.get("enrollment_date", "").strip()
        if enrollment_date:
            parsed_date = parse_date(enrollment_date)
            qs = qs.filter(enrollment_date=parsed_date) if parsed_date else qs.none()
        for parameter, lookup in (
            ("enrollment_date_from", "enrollment_date__gte"),
            ("enrollment_date_to", "enrollment_date__lte"),
        ):
            value = self.request.GET.get(parameter, "").strip()
            if value:
                parsed_date = parse_date(value)
                qs = qs.filter(**{lookup: parsed_date}) if parsed_date else qs.none()
        debt_status = self.request.GET.get("debt_status", "")
        if debt_status == "with_debt":
            qs = qs.filter(total_debt__gt=0)
        elif debt_status == "without_debt":
            qs = qs.filter(total_debt=0)
        qs = qs.distinct()
        sort = self.request.GET.get("sort", "created_at")
        direction = self.request.GET.get("direction", "desc")
        sort_field = self.sortable_fields.get(sort, "created_at")
        if direction not in {"asc", "desc"}:
            direction = "desc"
        if sort == "row_number":
            chronological_fields = ["enrollment_date", "created_at", "pk"]
            if direction == "desc":
                chronological_fields = [f"-{field}" for field in chronological_fields]
            return qs.order_by(*chronological_fields)
        if direction == "desc":
            sort_field = f"-{sort_field}"
        return qs.order_by(sort_field, "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from decimal import Decimal
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["pagination_query"] = query_params.urlencode()
        context["current_sort"] = self.request.GET.get("sort", "created_at")
        context["current_direction"] = self.request.GET.get("direction", "desc")
        context["course_filter_value"] = self.request.GET.get("course", "")
        course_id = self.request.GET.get("course_id", "")
        if course_id.isdigit():
            selected_course = Course.objects.filter(
                pk=course_id, campus=get_selected_campus(self.request)
            ).first()
            if selected_course:
                context["course_filter_value"] = selected_course.name
        context["promoter_filter_value"] = self.request.GET.get("promoter", "")
        promoter_id = self.request.GET.get("promoter_id", "")
        if promoter_id.isdigit():
            from .models import Promoter
            selected_promoter = Promoter.objects.filter(
                Q(campuses=get_selected_campus(self.request)) | Q(campuses__isnull=True),
                pk=promoter_id,
            ).first()
            if selected_promoter:
                context["promoter_filter_value"] = selected_promoter.name
        context["enrollment_date_filter_value"] = self.request.GET.get("enrollment_date", "")
        exact_enrollment_date = self.request.GET.get("enrollment_date", "")
        context["enrollment_date_from"] = self.request.GET.get("enrollment_date_from", "") or exact_enrollment_date
        context["enrollment_date_to"] = self.request.GET.get("enrollment_date_to", "") or exact_enrollment_date
        context["debt_filter_value"] = self.request.GET.get("debt_status", "")
        context["sort_urls"] = {}
        for key in self.sortable_fields:
            sort_params = self.request.GET.copy()
            sort_params.pop("page", None)
            if context["current_sort"] == key:
                next_direction = "desc" if context["current_direction"] == "asc" else "asc"
            else:
                next_direction = "asc"
            sort_params["sort"] = key
            sort_params["direction"] = next_direction
            context["sort_urls"][key] = f"?{sort_params.urlencode()}"
        chronological_ids = self.object_list.order_by(
            "enrollment_date", "created_at", "pk"
        ).values_list("pk", flat=True)
        row_numbers = {
            enrollment_id: row_number
            for row_number, enrollment_id in enumerate(chronological_ids, start=1)
        }
        for enrollment in context["enrollments"]:
            enrollment.row_number = row_numbers[enrollment.pk]
            installments = enrollment.installments.all()
            enrollment.has_outstanding_debt = enrollment.active and enrollment.total_debt > 0
            enrollment.has_no_debt = enrollment.active and enrollment.total_debt == 0
        context["payable_enrollment_ids"] = set()
        if self.request.user.is_superuser or self.request.user.can_register_payments:
            from payments.forms import pending_enrollments_for_campus
            context["payable_enrollment_ids"] = set(
                pending_enrollments_for_campus(get_selected_campus(self.request))
                .values_list("pk", flat=True)
            )
        return context


class StudentEnrollmentListView(EnrollmentListView):
    def get_student(self):
        if not hasattr(self, "student"):
            self.student = get_object_or_404(
                Student,
                pk=self.kwargs["student_id"],
                campus=get_selected_campus(self.request),
            )
        return self.student

    def get_queryset(self):
        self.get_student()
        return super().get_queryset().filter(student_id=self.student.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtered_student"] = self.get_student()
        return context


class EnrollmentExcelExportView(EnrollmentListView):
    def get(self, request, *args, **kwargs):
        self.request = request
        enrollments = list(
            self.get_queryset().filter(active=True).order_by("student__full_name", "pk")
        )
        row_numbers = {
            enrollment.pk: row_number
            for row_number, enrollment in enumerate(
                enrollments,
                start=1,
            )
        }
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Matrículas"
        worksheet.sheet_view.showGridLines = False
        worksheet.merge_cells("A1:M1")
        worksheet["A1"] = "Reporte de matrículas"
        worksheet["A1"].font = Font(bold=True, color="FFFFFF", size=16)
        worksheet["A1"].fill = PatternFill("solid", fgColor="173A72")
        worksheet.merge_cells("A2:M2")
        worksheet["A2"] = (
            f"Sede: {get_selected_campus(request).name} · "
            f"Exportado: {timezone.localdate():%d/%m/%Y}"
        )
        headers = [
            "N.º", "Estudiante", "Curso", "Código de ficha", "Promotores", "Fecha de matrícula",
            "Inicio", "Inscripción", "Mensualidad", "Pago total", "Pagado", "Deuda", "Recibos",
        ]
        for column, header in enumerate(headers, start=1):
            cell = worksheet.cell(row=4, column=column, value=header)
            cell.font = Font(bold=True, color="173A72")
            cell.fill = PatternFill("solid", fgColor="EAF1FF")

        for enrollment in enrollments:
            promoters = ", ".join(enrollment.promoter.values_list("name", flat=True)) or "—"
            receipts = ", ".join(
                f"{payment.receipt_number} (Anulado)"
                if payment.status == "ANULADO"
                else payment.receipt_number
                for payment in enrollment.payments.all()
            ) or "—"
            worksheet.append([
                row_numbers[enrollment.pk],
                enrollment.student.full_name,
                str(enrollment.course),
                enrollment.record_code or "—",
                promoters,
                enrollment.enrollment_date,
                enrollment.course.start_date,
                enrollment.enrollment_fee,
                enrollment.monthly_fee,
                enrollment.total_enrollment_cost,
                enrollment.total_paid,
                enrollment.total_debt,
                receipts,
            ])
            if enrollment.total_debt > 0:
                fill_color = "FFF3CD"
            else:
                fill_color = "D1E7DD"
            for cell in worksheet[worksheet.max_row]:
                cell.fill = PatternFill("solid", fgColor=fill_color)

        if enrollments:
            table = Table(
                displayName="EnrollmentTable",
                ref=f"A4:M{worksheet.max_row}",
            )
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            worksheet.add_table(table)
        else:
            worksheet["A4"] = "No hay matrículas que coincidan con los filtros."

        widths = [10, 30, 30, 18, 26, 18, 14, 15, 15, 15, 15, 15, 32]
        for column, width in enumerate(widths, start=1):
            worksheet.column_dimensions[get_column_letter(column)].width = width
        worksheet.freeze_panes = "A5"
        for row in worksheet.iter_rows(min_row=5, min_col=6, max_col=7):
            for cell in row:
                cell.number_format = "DD/MM/YYYY"
        for row in worksheet.iter_rows(min_row=5, min_col=8, max_col=12):
            for cell in row:
                cell.number_format = '"S/" #,##0.00'

        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="matriculas_{timezone.localdate():%Y%m%d}.xlsx"'
        )
        return response


class EnrollmentCreateView(CampusScopedMixin, CreateView):
    model = Enrollment
    form_class = EnrollmentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("enrollment-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        campus = get_selected_campus(self.request)
        form.instance.campus = campus
        form.instance.enrollment_fee = form.cleaned_data["enrollment_fee"]
        form.instance.monthly_fee = form.cleaned_data["monthly_fee"]
        try:
            with transaction.atomic():
                self.object = form.save()
                from payments.models import Installment
                if self.object.enrollment_fee > 0:
                    Installment.objects.create(
                        enrollment=self.object, concept="Matrícula",
                        amount=self.object.enrollment_fee, due_date=self.object.course.start_date,
                    )
                if self.object.monthly_fee > 0:
                    Installment.objects.create(
                        enrollment=self.object,
                        concept=f"Mensualidad inicial ({self.object.course.start_date:%Y-%m})",
                        amount=self.object.monthly_fee, due_date=self.object.course.start_date,
                    )
        except IntegrityError:
            form.add_error("course", "Este estudiante ya está matriculado en este curso.")
            return self.form_invalid(form)
        messages.success(self.request, "Matrícula registrada y cuotas iniciales generadas.")
        return redirect(self.get_success_url())


class EnrollmentUpdateView(CampusScopedMixin, UpdateView):
    model = Enrollment
    form_class = EnrollmentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("enrollment-list")

    def get_queryset(self):
        return self.campus_queryset(
            Enrollment.objects.select_related("campus", "student", "course")
            .prefetch_related("promoter")
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.campus = get_selected_campus(self.request)
        form.instance.enrollment_fee = form.cleaned_data["enrollment_fee"]
        form.instance.monthly_fee = form.cleaned_data["monthly_fee"]
        was_active = Enrollment.objects.filter(pk=form.instance.pk).values_list("active", flat=True).get()
        with transaction.atomic():
            response = super().form_valid(form)
            if not was_active and self.object.active:
                from payments.models import Installment
                Installment.objects.filter(enrollment=self.object).update(active=True)
        messages.success(self.request, "Matrícula actualizada correctamente.")
        return response


class EnrollmentDeleteView(CampusScopedMixin, DeleteView):
    model = Enrollment
    template_name = "students/enrollment_confirm_delete.html"
    success_url = reverse_lazy("enrollment-list")

    def get_queryset(self):
        return self.campus_queryset(
            Enrollment.objects.select_related("campus", "student", "course")
        )

    def post(self, request, *args, **kwargs):
        enrollment = self.get_object()
        self.object = enrollment
        from payments.models import Installment, Payment
        with transaction.atomic():
            enrollment.active = False
            enrollment.save(update_fields=["active"])
            Installment.objects.filter(enrollment=enrollment).update(active=False)
            Payment.objects.filter(
                enrollment=enrollment,
                status=Payment.Status.CONFIRMED,
            ).update(status=Payment.Status.VOID)
        messages.success(self.request, "Matrícula dada de baja; se conservaron las cuotas y recibos, y los recibos confirmados se anularon.")
        return redirect(self.get_success_url())


def course_students_queryset(request):
    campus = get_selected_campus(request)
    enrollments = (
        Enrollment.objects.filter(campus=campus, active=True, student__active=True)
        .select_related("student", "course")
        .order_by("student__full_name")
    )
    qs = (
        Course.objects.filter(campus=campus, active=True)
        .annotate(
            student_count=Count(
                "enrollments",
                filter=Q(enrollments__active=True, enrollments__student__active=True),
            )
        )
        .prefetch_related(Prefetch("enrollments", queryset=enrollments))
        .order_by("name", "schedule", "group")
    )
    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(schedule__icontains=query) | Q(group__icontains=query))
    return qs


class CourseStudentTablesView(CampusScopedMixin, ListView):
    """Muestra una tabla independiente por curso para la sede seleccionada."""
    model = Course
    template_name = "students/course_student_tables.html"
    context_object_name = "courses"

    def get_queryset(self):
        return course_students_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["total_students"] = Enrollment.objects.filter(
            campus=get_selected_campus(self.request), active=True, student__active=True
        ).values("student_id").distinct().count()
        return context


class CourseStudentExportView(CampusScopedMixin, View):
    def get(self, request, *args, **kwargs):
        workbook = Workbook()
        courses = list(course_students_queryset(request).filter(student_count__gt=0))
        grouped_courses = [
            (name, list(course_group))
            for name, course_group in groupby(courses, key=lambda course: course.name)
        ]
        workbook.remove(workbook.active)
        campus_name = get_selected_campus(request).name
        export_date = timezone.localdate()
        used_titles = set()

        if not grouped_courses:
            worksheet = workbook.create_sheet("Sin cursos")
            worksheet["A1"] = "No hay cursos activos para exportar."

        for course_name, same_name_courses in grouped_courses:
            base_title = re.sub(r"[\[\]:*?/\\]", " ", course_name)
            base_title = "".join(character if character.isprintable() else " " for character in base_title).strip(" '") or "Curso"
            title = base_title[:31]
            suffix_number = 2
            while title.casefold() in used_titles:
                suffix = f" ({suffix_number})"
                title = f"{base_title[:31 - len(suffix)]}{suffix}"
                suffix_number += 1
            used_titles.add(title.casefold())

            worksheet = workbook.create_sheet(title)
            worksheet.sheet_view.showGridLines = False
            worksheet.merge_cells("A1:E1")
            worksheet["A1"] = course_name
            worksheet["A1"].font = Font(bold=True, color="FFFFFF", size=16)
            worksheet["A1"].fill = PatternFill("solid", fgColor="173A72")
            worksheet.merge_cells("A2:E2")
            worksheet["A2"] = f"Sede: {campus_name} · Exportado: {export_date:%d/%m/%Y}"

            for course in same_name_courses:
                section_row = worksheet.max_row + 2
                section_details = [f"Grupo: {course.group or '—'}", f"Horario: {course.schedule or '—'}"]
                section_details.extend([
                    f"Capacidad: {course.capacity}",
                    f"Inicio: {course.start_date:%d/%m/%Y}",
                ])
                worksheet.merge_cells(
                    start_row=section_row, start_column=1, end_row=section_row, end_column=5
                )
                section = worksheet.cell(row=section_row, column=1, value=" · ".join(section_details))
                section.font = Font(bold=True, color="FFFFFF")
                section.fill = PatternFill("solid", fgColor="1E9E6A")

                headers = ["N.º", "Alumno", "DNI", "Teléfonos", "Fecha de matrícula"]
                header_row = section_row + 1
                for column, header in enumerate(headers, start=1):
                    cell = worksheet.cell(row=header_row, column=column, value=header)
                    cell.font = Font(bold=True, color="173A72")
                    cell.fill = PatternFill("solid", fgColor="EAF1FF")

                course_enrollments = list(course.enrollments.all())
                for row_number, enrollment in enumerate(course_enrollments, start=1):
                    worksheet.append([
                        row_number,
                        enrollment.student.full_name,
                        enrollment.student.document_number,
                        enrollment.student.phone,
                        enrollment.enrollment_date,
                    ])

                table = Table(
                    displayName=f"Course_{course.pk}",
                    ref=f"A{header_row}:E{worksheet.max_row}",
                )
                table.tableStyleInfo = TableStyleInfo(
                    name="TableStyleMedium2",
                    showFirstColumn=False,
                    showLastColumn=False,
                    showRowStripes=True,
                    showColumnStripes=False,
                )
                worksheet.add_table(table)

            worksheet.freeze_panes = "A5"
            widths = [10, 32, 18, 16, 22]
            for column, width in enumerate(widths, start=1):
                worksheet.column_dimensions[get_column_letter(column)].width = width
            for row in worksheet.iter_rows(min_row=5):
                row[4].number_format = "DD/MM/YYYY"

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="alumnos_por_curso_{timezone.localdate():%Y%m%d}.xlsx"'
        workbook.save(response)
        return response


class AvailableStudentsForCourseView(CampusScopedMixin, ListView):
    """Devuelve por AJAX los alumnos de la sede aún no inscritos al curso."""
    def get(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        course_id = request.GET.get("course_id")
        if not course_id:
            return JsonResponse({"students": []})
        course = Course.objects.filter(pk=course_id, campus=campus, active=True).first()
        if course is None:
            return JsonResponse({"students": []}, status=400)
        enrollments = Enrollment.objects.filter(course=course)
        current_enrollment = None
        enrollment_id = request.GET.get("enrollment_id")
        if enrollment_id:
            current_enrollment = enrollments.filter(pk=enrollment_id, campus=campus).first()
        if current_enrollment:
            enrollments = enrollments.exclude(pk=current_enrollment.pk)
        enrolled_ids = enrollments.values_list("student_id", flat=True)
        students = Student.objects.filter(campus=campus, active=True)
        if current_enrollment:
            students = Student.objects.filter(campus=campus).filter(
                Q(active=True) | Q(pk=current_enrollment.student_id)
            )
        students = students.exclude(
            pk__in=enrolled_ids
        ).order_by("full_name").values("id", "full_name")
        return JsonResponse({"students": list(students)})
