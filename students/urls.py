from django.urls import path
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
    path("herramientas/", ToolsView.as_view(), name="tools"),
]
