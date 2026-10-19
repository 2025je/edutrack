from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.views.generic import TemplateView

from core.campus import get_selected_campus
from payments.models import Payment

from .models import EMPTY_VALUE, Course, Enrollment, Promoter
from .views import CampusScopedMixin


def month_label(value):
    return value.strftime("%m/%Y") if value else EMPTY_VALUE


def money(value):
    return f"{(value or Decimal('0')):.2f}"


class SimpleReportView(CampusScopedMixin, TemplateView):
    """Informe tabular de una sola tabla para la sede seleccionada."""

    template_name = "students/report_table.html"
    title = ""
    description = ""
    columns = ()
    numeric_columns = ()
    empty_message = "No hay datos para mostrar."

    def build(self, campus):
        """Devuelve (filas, fila_de_totales o None)."""
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows, totals = self.build(get_selected_campus(self.request))
        context.update(
            title=self.title,
            description=self.description,
            columns=self.columns,
            numeric_columns=self.numeric_columns,
            rows=rows,
            totals=totals,
            empty_message=self.empty_message,
        )
        return context


class EnrollmentsByPromoterReportView(SimpleReportView):
    required_permission = "core.view_academic_reports"
    title = "Matrículas por promotor"
    description = "Matrículas activas de la sede agrupadas por promotor."
    columns = ("Promotor", "Matrículas", "Con estudiante", "Vacantes reservadas")
    numeric_columns = (1, 2, 3)

    def build(self, campus):
        promoters = (
            Promoter.objects.filter(enrollments__campus=campus, enrollments__active=True)
            .annotate(
                total=Count("enrollments", distinct=True),
                with_student=Count(
                    "enrollments", filter=Q(enrollments__student__isnull=False), distinct=True
                ),
            )
            .order_by("-total", "name")
        )
        rows = [[p.name, p.total, p.with_student, p.total - p.with_student] for p in promoters]
        without = Enrollment.objects.filter(campus=campus, active=True, promoter__isnull=True)
        total = without.count()
        if total:
            with_student = without.filter(student__isnull=False).count()
            rows.append(["Sin promotor", total, with_student, total - with_student])
        totals = ["Total de matrículas"] + [sum(row[i] for row in rows) for i in (1, 2, 3)]
        return rows, None if not rows else totals


class EnrollmentsByMonthReportView(SimpleReportView):
    required_permission = "core.view_academic_reports"
    title = "Matrículas por mes"
    description = "Evolución mensual de las matrículas activas de la sede."
    columns = ("Mes", "Matrículas", "Con estudiante", "Vacantes reservadas", "Sin curso")
    numeric_columns = (1, 2, 3, 4)

    def build(self, campus):
        data = (
            Enrollment.objects.filter(campus=campus, active=True)
            .annotate(month=TruncMonth("enrollment_date"))
            .values("month")
            .annotate(
                total=Count("id"),
                with_student=Count("id", filter=Q(student__isnull=False)),
                pending=Count("id", filter=Q(course__isnull=True)),
            )
            .order_by("-month")
        )
        rows = [
            [
                month_label(item["month"]),
                item["total"],
                item["with_student"],
                item["total"] - item["with_student"],
                item["pending"],
            ]
            for item in data
        ]
        totals = ["Total"] + [sum(row[i] for row in rows) for i in (1, 2, 3, 4)]
        return rows, None if not rows else totals


class PendingCourseReportView(SimpleReportView):
    required_permission = "core.view_academic_reports"
    title = "Estudiantes pendientes de curso"
    description = "Matrículas activas con estudiante que todavía no tienen curso asignado."
    columns = ("Estudiante", "DNI", "Teléfonos", "Fecha de matrícula")
    empty_message = "No hay matrículas pendientes de asignación."

    def build(self, campus):
        enrollments = (
            Enrollment.objects.filter(
                campus=campus, active=True, course__isnull=True, student__isnull=False
            )
            .select_related("student")
            .order_by("enrollment_date", "student__full_name")
        )
        rows = [
            [
                e.student.full_name,
                e.student.document_number or EMPTY_VALUE,
                e.student.phone or EMPTY_VALUE,
                e.enrollment_date.strftime("%d/%m/%Y"),
            ]
            for e in enrollments
        ]
        return rows, None if not rows else [f"{len(rows)} estudiante(s)", "", "", ""]


class IncomeByMonthReportView(SimpleReportView):
    required_permission = "core.view_financial_reports"
    title = "Ingresos por mes"
    description = "Pagos confirmados de la sede agrupados por mes. Los anulados no se cuentan."
    columns = ("Mes", "Pagos", "Total recaudado")
    numeric_columns = (1, 2)

    def build(self, campus):
        data = (
            Payment.objects.filter(campus=campus, status=Payment.Status.CONFIRMED)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"), total=Sum("amount"))
            .order_by("-month")
        )
        rows = [[month_label(i["month"]), i["count"], money(i["total"])] for i in data]
        if not rows:
            return rows, None
        grand = sum((i["total"] or Decimal("0")) for i in data)
        return rows, ["Total", sum(i["count"] for i in data), money(grand)]


class DebtByCourseReportView(SimpleReportView):
    required_permission = "core.view_pending_balances"
    title = "Morosidad por curso"
    description = "Saldo pendiente de las matrículas con deuda, agrupado por curso."
    columns = ("Curso", "Grupo", "Horario", "Matrículas con deuda", "Saldo pendiente")
    numeric_columns = (3, 4)
    empty_message = "No hay saldos pendientes."

    def build(self, campus):
        from payments.forms import pending_enrollments_for_campus

        grouped = {}
        enrollments = pending_enrollments_for_campus(campus).select_related("course")
        for enrollment in enrollments:
            entry = grouped.setdefault(enrollment.course_id, [enrollment.course, 0, Decimal("0")])
            entry[1] += 1
            entry[2] += enrollment.pending_balance
        ordered = sorted(grouped.values(), key=lambda e: (-e[2], e[0].name))
        rows = [
            [c.name, c.group or EMPTY_VALUE, c.schedule, count, money(total)]
            for c, count, total in ordered
        ]
        if not rows:
            return rows, None
        return rows, [
            "Total",
            "",
            "",
            sum(e[1] for e in ordered),
            money(sum(e[2] for e in ordered)),
        ]


class CourseOccupancyReportView(SimpleReportView):
    required_permission = "core.view_academic_reports"
    title = "Ocupación de cupos por curso"
    description = (
        "Porcentaje de ocupación de cada curso activo y fechas de la primera y la última matrícula."
    )
    columns = (
        "Curso",
        "Grupo",
        "Horario",
        "Capacidad",
        "Ocupadas",
        "Ocupación",
        "Primera matrícula",
        "Última matrícula",
    )
    numeric_columns = (3, 4, 5)
    empty_message = "No hay cursos activos."

    def build(self, campus):
        from django.db.models import Max, Min

        courses = (
            Course.objects.filter(campus=campus, active=True)
            .annotate(
                occupied=Count(
                    "enrollments",
                    filter=Q(enrollments__active=True)
                    & (Q(enrollments__student__isnull=True) | Q(enrollments__student__active=True)),
                ),
                first_date=Min("enrollments__enrollment_date", filter=Q(enrollments__active=True)),
                last_date=Max("enrollments__enrollment_date", filter=Q(enrollments__active=True)),
            )
            .order_by("name", "schedule", "group")
        )

        def day(value):
            return value.strftime("%d/%m/%Y") if value else EMPTY_VALUE

        rows = [
            [
                c.name,
                c.group or EMPTY_VALUE,
                c.schedule,
                c.capacity or EMPTY_VALUE,
                c.occupied,
                f"{c.occupied * 100 / c.capacity:.0f}%" if c.capacity else EMPTY_VALUE,
                day(c.first_date),
                day(c.last_date),
            ]
            for c in courses
        ]
        return rows, None
