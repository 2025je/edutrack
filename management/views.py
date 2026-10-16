from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, Count, IntegerField, Q, When
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import Campus, User
from students.models import (
    UNASSIGNED_COURSE_NAME,
    UNASSIGNED_SCHEDULE_NAME,
    Course,
    Promoter,
    Schedule,
)

from .forms import (
    CampusForm,
    CourseForm,
    CourseStartDateForm,
    PromoterForm,
    ScheduleForm,
    UserCampusesForm,
    UserCreateForm,
)


class CampusManagementMixin(FeaturePermissionMixin):
    permission_field = "can_manage_campuses"


class CatalogManagerMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin, LoginRequiredMixin):
    permission_field = "can_manage_promoters"


# Sedes


class CampusListView(CampusManagementMixin, ListView):
    template_name = "management/campus_list.html"
    context_object_name = "campuses"

    def get_queryset(self):
        return Campus.objects.annotate(users_count=Count("users", distinct=True))


class CampusCreateView(CampusManagementMixin, CreateView):
    model = Campus
    form_class = CampusForm
    template_name = "management/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def form_valid(self, form):
        messages.success(self.request, "Sede creada correctamente.")
        return super().form_valid(form)


class CampusUpdateView(CampusManagementMixin, UpdateView):
    model = Campus
    form_class = CampusForm
    template_name = "management/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def form_valid(self, form):
        messages.success(self.request, "Sede actualizada correctamente.")
        return super().form_valid(form)


class CampusUserListView(CampusManagementMixin, ListView):
    template_name = "management/campus_users.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        users = User.objects.filter(is_superuser=False).prefetch_related("campuses")
        q = self.request.GET.get("q", "").strip()
        if q:
            users = users.filter(username__icontains=q)
        return users.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class CampusUserUpdateView(CampusManagementMixin, UpdateView):
    form_class = UserCampusesForm
    template_name = "management/campus_user_form.html"
    context_object_name = "target_user"
    success_url = reverse_lazy("campus-users")

    # Los superusuarios ven todas las sedes y no se administran desde aquí.
    queryset = User.objects.filter(is_superuser=False)

    def form_valid(self, form):
        messages.success(self.request, "Sedes del usuario actualizadas.")
        return super().form_valid(form)


# Usuarios


class UserCreateView(FeaturePermissionMixin, CreateView):
    permission_field = "can_manage_users"
    form_class = UserCreateForm
    template_name = "management/user_form.html"
    success_url = reverse_lazy("user-create")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Usuario «{self.object.username}» creado.")
        return response


# Catálogo


class CourseCreateView(CatalogManagerMixin, TemplateView):
    template_name = "management/courses.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        context["form"] = form or CourseForm(
            campus=campus, initial={"schedule": self.request.GET.get("schedule")}
        )
        context["courses"] = (
            Course.objects.filter(campus=campus)
            .annotate(
                is_unassigned_course=Case(
                    When(name=UNASSIGNED_COURSE_NAME, schedule=UNASSIGNED_SCHEDULE_NAME, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            )
            .order_by("is_unassigned_course", "name", "schedule", "group")
        )
        return context

    def post(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        form = CourseForm(request.POST, campus=campus)
        if form.is_valid():
            course = form.save(commit=False)
            course.campus = campus
            course.save()
            messages.success(request, f"Curso «{course.name}» creado.")
            return redirect("course-list")
        return self.render_to_response(self.get_context_data(form=form))


class CourseStartDateUpdateView(CatalogManagerMixin, UpdateView):
    template_name = "management/course_edit.html"
    form_class = CourseStartDateForm
    success_url = reverse_lazy("course-list")

    def get_queryset(self):
        return Course.objects.filter(campus=get_selected_campus(self.request)).exclude(
            name=UNASSIGNED_COURSE_NAME, schedule=UNASSIGNED_SCHEDULE_NAME
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Curso «{self.object.name}» actualizado.")
        return response


class ScheduleCreateView(CatalogManagerMixin, TemplateView):
    template_name = "management/schedule_form.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = form or ScheduleForm()
        context["schedules"] = Schedule.objects.order_by("name")
        return context

    def post(self, request, *args, **kwargs):
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save()
            messages.success(request, f"Horario «{schedule.name}» creado.")
            return redirect(f"{reverse('course-list')}?schedule={schedule.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class PromoterView(CatalogManagerMixin, TemplateView):
    template_name = "management/promoters.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        context["form"] = form or PromoterForm()
        context["promoters"] = Promoter.objects.filter(
            Q(campuses=campus) | Q(campuses__isnull=True)
        ).distinct()
        return context

    def post(self, request, *args, **kwargs):
        form = PromoterForm(request.POST)
        if form.is_valid():
            promoter = form.save()
            promoter.campuses.add(get_selected_campus(request))
            messages.success(request, f"Promotor «{promoter.name}» creado.")
            return redirect("promoter-list")
        return self.render_to_response(self.get_context_data(form=form))
