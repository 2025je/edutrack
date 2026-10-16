from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.campus import FeaturePermissionMixin
from core.models import Campus, User

from .forms import CampusForm, UserCampusesForm


class CampusManagementMixin(FeaturePermissionMixin):
    permission_field = "can_manage_campuses"


class CampusListView(CampusManagementMixin, ListView):
    template_name = "sedes/campus_list.html"
    context_object_name = "campuses"

    def get_queryset(self):
        return Campus.objects.annotate(users_count=Count("users", distinct=True))


class CampusCreateView(CampusManagementMixin, CreateView):
    model = Campus
    form_class = CampusForm
    template_name = "sedes/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def form_valid(self, form):
        messages.success(self.request, "Sede creada correctamente.")
        return super().form_valid(form)


class CampusUpdateView(CampusManagementMixin, UpdateView):
    model = Campus
    form_class = CampusForm
    template_name = "sedes/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def form_valid(self, form):
        messages.success(self.request, "Sede actualizada correctamente.")
        return super().form_valid(form)


class CampusUserListView(CampusManagementMixin, ListView):
    template_name = "sedes/campus_users.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        users = User.objects.filter(is_superuser=False).prefetch_related("campuses")
        q = self.request.GET.get("q", "").strip()
        if q:
            users = users.filter(
                Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
        return users.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class CampusUserUpdateView(CampusManagementMixin, UpdateView):
    form_class = UserCampusesForm
    template_name = "sedes/campus_user_form.html"
    context_object_name = "target_user"
    success_url = reverse_lazy("campus-users")

    # Los superusuarios ven todas las sedes y no se administran desde aquí.
    queryset = User.objects.filter(is_superuser=False)

    def form_valid(self, form):
        messages.success(self.request, "Sedes del usuario actualizadas.")
        return super().form_valid(form)
