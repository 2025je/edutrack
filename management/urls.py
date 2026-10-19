from django.urls import path

from .views import (
    ActivityLogView,
    RecordHistoryView,
    CampusCreateView,
    CampusFlyerCreateView,
    CampusFlyerDeleteView,
    CampusListView,
    CampusUpdateView,
    CourseCreateView,
    CourseStartDateUpdateView,
    PromoterView,
    ScheduleCreateView,
    UserCreateView,
    UserListView,
    UserUpdateView,
)

urlpatterns = [
    path("sedes/", CampusListView.as_view(), name="campus-list"),
    path("sedes/nueva/", CampusCreateView.as_view(), name="campus-create"),
    path("sedes/<int:pk>/editar/", CampusUpdateView.as_view(), name="campus-update"),
    path("sedes/<int:pk>/volantes/", CampusFlyerCreateView.as_view(), name="campus-flyer-create"),
    path(
        "sedes/volantes/<int:pk>/eliminar/",
        CampusFlyerDeleteView.as_view(),
        name="campus-flyer-delete",
    ),
    path("actividad/", ActivityLogView.as_view(), name="activity-log"),
    path("historial/<str:kind>/<int:pk>/", RecordHistoryView.as_view(), name="record-history"),
    path("usuarios/", UserListView.as_view(), name="user-list"),
    path("usuarios/nuevo/", UserCreateView.as_view(), name="user-create"),
    path("usuarios/<int:pk>/editar/", UserUpdateView.as_view(), name="user-update"),
    path("catalogo/horarios/nuevo/", ScheduleCreateView.as_view(), name="schedule-create"),
    path("catalogo/promotores/", PromoterView.as_view(), name="promoter-list"),
    path("catalogo/cursos/", CourseCreateView.as_view(), name="course-list"),
    path(
        "catalogo/cursos/<int:pk>/editar/",
        CourseStartDateUpdateView.as_view(),
        name="course-update",
    ),
]
