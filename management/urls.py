from django.urls import path

from .views import (
    CampusCreateView,
    CampusListView,
    CampusUpdateView,
    CampusUserListView,
    CampusUserUpdateView,
    CourseCreateView,
    CourseStartDateUpdateView,
    PromoterView,
    ScheduleCreateView,
    UserCreateView,
)

urlpatterns = [
    path("sedes/", CampusListView.as_view(), name="campus-list"),
    path("sedes/nueva/", CampusCreateView.as_view(), name="campus-create"),
    path("sedes/<int:pk>/editar/", CampusUpdateView.as_view(), name="campus-update"),
    path("sedes/usuarios/", CampusUserListView.as_view(), name="campus-users"),
    path("sedes/usuarios/<int:pk>/", CampusUserUpdateView.as_view(), name="campus-user-update"),
    path("usuarios/nuevo/", UserCreateView.as_view(), name="user-create"),
    path("catalogo/horarios/nuevo/", ScheduleCreateView.as_view(), name="schedule-create"),
    path("catalogo/promotores/", PromoterView.as_view(), name="promoter-list"),
    path("catalogo/cursos/", CourseCreateView.as_view(), name="course-list"),
    path(
        "catalogo/cursos/<int:pk>/editar/",
        CourseStartDateUpdateView.as_view(),
        name="course-update",
    ),
]
