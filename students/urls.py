from django.urls import path
from .views import StudentListView, StudentCreateView, EnrollmentListView, EnrollmentCreateView, CourseStudentTablesView, AvailableStudentsForCourseView

urlpatterns = [
    path("", StudentListView.as_view(), name="student-list"),
    path("nuevo/", StudentCreateView.as_view(), name="student-create"),
    path("matriculas/", EnrollmentListView.as_view(), name="enrollment-list"),
    path("matriculas/nueva/", EnrollmentCreateView.as_view(), name="enrollment-create"),
    path("matriculas/alumnos-disponibles/", AvailableStudentsForCourseView.as_view(), name="course-students-available"),
    path("reportes/alumnos-por-curso/", CourseStudentTablesView.as_view(), name="course-student-tables"),
]
