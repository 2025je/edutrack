from django.urls import path

from .views import CourseCreateView, PromoterView, ScheduleCreateView

urlpatterns = [
    path("horarios/nuevo/", ScheduleCreateView.as_view(), name="schedule-create"),
    path("promotores/", PromoterView.as_view(), name="promoter-list"),
    path("cursos/", CourseCreateView.as_view(), name="course-list"),
]
