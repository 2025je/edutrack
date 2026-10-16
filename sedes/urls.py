from django.urls import path

from .views import (
    CampusCreateView,
    CampusListView,
    CampusUpdateView,
    CampusUserListView,
    CampusUserUpdateView,
)

urlpatterns = [
    path("", CampusListView.as_view(), name="campus-list"),
    path("nueva/", CampusCreateView.as_view(), name="campus-create"),
    path("<int:pk>/editar/", CampusUpdateView.as_view(), name="campus-update"),
    path("usuarios/", CampusUserListView.as_view(), name="campus-users"),
    path("usuarios/<int:pk>/", CampusUserUpdateView.as_view(), name="campus-user-update"),
]
