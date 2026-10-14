from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import DashboardView, select_campus
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/ingresar/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("cuentas/salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("sedes/seleccionar/", select_campus, name="select-campus"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("estudiantes/", include("students.urls")),
    path("pagos/", include("payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
