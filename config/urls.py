from django.contrib import admin
from django.http import Http404
from django.urls import path, include, re_path
from django.views.defaults import page_not_found
from django.conf import settings
from django.conf.urls.static import static
from core.views import DashboardView, GlobalSearchView, select_campus
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "cuentas/ingresar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("cuentas/salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("sedes/seleccionar/", select_campus, name="select-campus"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("buscar/", GlobalSearchView.as_view(), name="global-search"),
    path("estudiantes/", include("students.urls")),
    path("pagos/", include("payments.urls")),
    path("llamadas/", include("calls.urls")),
    path("", include("management.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# También en DEBUG se muestra la página 404 amigable en lugar de la técnica de Django.
urlpatterns += [re_path(r"^.*$", page_not_found, {"exception": Http404()})]
