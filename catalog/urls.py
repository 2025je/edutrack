from django.urls import path

from .views import CourseCreateView, CourseStartDateUpdateView, PromoterView, ScheduleCreateView

urlpatterns = [
    path("horarios/nuevo/", ScheduleCreateView.as_view(), name="schedule-create"),
    path("promotores/", PromoterView.as_view(), name="promoter-list"),
    path("cursos/", CourseCreateView.as_view(), name="course-list"),
    path("cursos/<int:pk>/editar/", CourseStartDateUpdateView.as_view(), name="course-update"),
]
