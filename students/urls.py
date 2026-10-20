from django.urls import path
from .duplicates import StudentDuplicatesView
from .importer import StudentImportView
from .timeline import StudentTimelineView
from .lifecycle import (
    EnrollmentTransferView,
    RestoreEnrollmentView,
    RestoreStudentView,
    TrashView,
)
from .reports import (
    CourseOccupancyReportView,
    DebtByCourseReportView,
    EnrollmentsByMonthReportView,
    EnrollmentsByPromoterReportView,
    IncomeByMonthReportView,
    PendingCourseReportView,
)
from .views import (
    StudentListView,
    StudentCreateView,
    StudentUpdateView,
    StudentDeleteView,
    EnrollmentListView,
    StudentEnrollmentListView,
    EnrollmentExcelExportView,
    EnrollmentCreateView,
    EnrollmentUpdateView,
    EnrollmentDeleteView,
    CourseStudentTablesView,
    CourseStudentExportView,
    AvailableStudentsForCourseView,
    ToolsView,
)

urlpatterns = [
    path("", StudentListView.as_view(), name="student-list"),
    path("importar/", StudentImportView.as_view(), name="student-import"),
    path("duplicados/", StudentDuplicatesView.as_view(), name="student-duplicates"),
    path("<int:pk>/historial/", StudentTimelineView.as_view(), name="student-timeline"),
    path("nuevo/", StudentCreateView.as_view(), name="student-create"),
    path("<int:pk>/editar/", StudentUpdateView.as_view(), name="student-update"),
    path("<int:pk>/eliminar/", StudentDeleteView.as_view(), name="student-delete"),
    path("matriculas/", EnrollmentListView.as_view(), name="enrollment-list"),
    path(
        "matriculas/estudiante/<int:student_id>/",
        StudentEnrollmentListView.as_view(),
        name="student-enrollment-list",
    ),
    path(
        "matriculas/exportar-excel/", EnrollmentExcelExportView.as_view(), name="enrollment-excel"
    ),
    path(
        "matriculas/<int:pk>/trasladar/",
        EnrollmentTransferView.as_view(),
        name="enrollment-transfer",
    ),
    path(
        "matriculas/<int:pk>/restaurar/", RestoreEnrollmentView.as_view(), name="enrollment-restore"
    ),
    path("<int:pk>/restaurar/", RestoreStudentView.as_view(), name="student-restore"),
    path("papelera/", TrashView.as_view(), name="trash"),
    path("matriculas/nueva/", EnrollmentCreateView.as_view(), name="enrollment-create"),
    path("matriculas/<int:pk>/editar/", EnrollmentUpdateView.as_view(), name="enrollment-update"),
    path("matriculas/<int:pk>/eliminar/", EnrollmentDeleteView.as_view(), name="enrollment-delete"),
    path(
        "matriculas/alumnos-disponibles/",
        AvailableStudentsForCourseView.as_view(),
        name="course-students-available",
    ),
    path(
        "reportes/alumnos-por-curso/exportar/",
        CourseStudentExportView.as_view(),
        name="course-student-export",
    ),
    path(
        "reportes/alumnos-por-curso/",
        CourseStudentTablesView.as_view(),
        name="course-student-tables",
    ),
    path(
        "reportes/matriculas-por-promotor/",
        EnrollmentsByPromoterReportView.as_view(),
        name="report-enrollments-by-promoter",
    ),
    path(
        "reportes/matriculas-por-mes/",
        EnrollmentsByMonthReportView.as_view(),
        name="report-enrollments-by-month",
    ),
    path(
        "reportes/pendientes-de-curso/",
        PendingCourseReportView.as_view(),
        name="report-pending-course",
    ),
    path(
        "reportes/ingresos-por-mes/",
        IncomeByMonthReportView.as_view(),
        name="report-income-by-month",
    ),
    path(
        "reportes/morosidad-por-curso/",
        DebtByCourseReportView.as_view(),
        name="report-debt-by-course",
    ),
    path(
        "reportes/ocupacion-por-curso/",
        CourseOccupancyReportView.as_view(),
        name="report-course-occupancy",
    ),
    path("herramientas/", ToolsView.as_view(), name="tools"),
]
