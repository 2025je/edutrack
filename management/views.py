from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.dateparse import parse_date
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import ActivityLog, Campus, CampusFlyer, User
from core.pagination import paginate_context
from students.models import Course, Promoter, Schedule

from .forms import (
    CampusFlyerForm,
    CampusForm,
    CourseForm,
    CourseStartDateForm,
    PromoterForm,
    ScheduleForm,
    UserCreateForm,
    UserUpdateForm,
)


class CampusManagementMixin(FeaturePermissionMixin):
    required_permission = "core.change_campus"


class CatalogManagerMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin, LoginRequiredMixin):
    required_permission = "students.view_course"
    method_permissions = {"POST": "students.add_course"}


def manageable_users(editor):
    """Usuarios editables: nunca superusuarios, y el personal de admin solo por superusuarios."""
    users = User.objects.filter(is_superuser=False)
    return users if editor.is_superuser else users.filter(is_staff=False)


# Sedes


class CampusListView(CampusManagementMixin, ListView):
    required_permission = "core.view_campus"
    template_name = "management/campus_list.html"
    context_object_name = "campuses"
    paginate_by = 20

    def get_queryset(self):
        return (
            Campus.objects.annotate(users_count=Count("users", distinct=True))
            .prefetch_related("flyers")
            .order_by("name")
        )


class CampusCreateView(CampusManagementMixin, CreateView):
    required_permission = "core.add_campus"
    model = Campus
    form_class = CampusForm
    template_name = "management/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("flyer_form", CampusFlyerForm(prefix="flyer", optional=True))
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        flyer_form = CampusFlyerForm(request.POST, request.FILES, prefix="flyer", optional=True)
        # El volante es opcional: solo se valida si se llenó algún campo.
        flyer_given = flyer_form.has_changed()
        if form.is_valid() and (not flyer_given or flyer_form.is_valid()):
            with transaction.atomic():
                self.object = form.save()
                if flyer_given:
                    flyer = flyer_form.save(commit=False)
                    flyer.campus = self.object
                    flyer.save()
            messages.success(request, "Sede creada correctamente.")
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form, flyer_form=flyer_form))


class CampusUpdateView(CampusManagementMixin, UpdateView):
    model = Campus
    form_class = CampusForm
    template_name = "management/campus_form.html"
    success_url = reverse_lazy("campus-list")

    def form_valid(self, form):
        messages.success(self.request, "Sede actualizada correctamente.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["flyers"] = self.object.flyers.all()
        context["flyer_form"] = CampusFlyerForm()
        return context


class CampusFlyerCreateView(CampusManagementMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        campus = get_object_or_404(Campus, pk=pk)
        form = CampusFlyerForm(request.POST, request.FILES)
        if form.is_valid():
            flyer = form.save(commit=False)
            flyer.campus = campus
            flyer.save()
            messages.success(request, f"Volante «{flyer.title}» subido.")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return redirect("campus-update", pk=campus.pk)


class CampusFlyerDeleteView(CampusManagementMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        flyer = get_object_or_404(CampusFlyer, pk=pk)
        campus_pk = flyer.campus_id
        flyer.file.delete(save=False)
        flyer.delete()
        messages.success(request, "Volante eliminado.")
        return redirect("campus-update", pk=campus_pk)


# Usuarios


class UserManagementMixin(FeaturePermissionMixin):
    required_permission = "core.manage_user_access"


class UserListView(UserManagementMixin, ListView):
    required_permission = "core.view_user"
    template_name = "management/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        users = manageable_users(self.request.user).prefetch_related("campuses")
        q = self.request.GET.get("q", "").strip()
        if q:
            users = users.filter(username__icontains=q)
        return users.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class UserCreateView(UserManagementMixin, CreateView):
    form_class = UserCreateForm
    template_name = "management/user_form.html"
    success_url = reverse_lazy("user-list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Usuario «{self.object.username}» creado.")
        return response


class UserUpdateView(UserManagementMixin, UpdateView):
    form_class = UserUpdateForm
    template_name = "management/user_form.html"
    context_object_name = "target_user"
    success_url = reverse_lazy("user-list")

    def get_queryset(self):
        return manageable_users(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Usuario «{self.object.username}» actualizado.")
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
        courses = Course.objects.filter(campus=campus).order_by("name", "schedule", "group")
        context.update(paginate_context(self.request, courses, 25))
        context["courses"] = context["page_obj"]
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
    required_permission = "students.change_course"
    method_permissions = {}
    template_name = "management/course_edit.html"
    form_class = CourseStartDateForm
    success_url = reverse_lazy("course-list")

    def get_queryset(self):
        return Course.objects.filter(campus=get_selected_campus(self.request))

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Curso «{self.object.name}» actualizado.")
        return response


class ScheduleCreateView(CatalogManagerMixin, TemplateView):
    required_permission = "students.add_course"
    method_permissions = {}
    template_name = "management/schedule_form.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        context["form"] = form or ScheduleForm(campus=campus)
        schedules = Schedule.objects.filter(campus=campus).order_by("name")
        context.update(paginate_context(self.request, schedules, 25))
        context["schedules"] = context["page_obj"]
        return context

    def post(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        form = ScheduleForm(request.POST, campus=campus)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.campus = campus
            schedule.save()
            messages.success(request, f"Horario «{schedule.name}» creado.")
            return redirect(f"{reverse('course-list')}?schedule={schedule.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class PromoterView(CatalogManagerMixin, TemplateView):
    required_permission = "students.view_promoter"
    method_permissions = {"POST": "students.add_promoter"}
    template_name = "management/promoters.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        context["form"] = form or PromoterForm()
        promoters = (
            Promoter.objects.filter(Q(campuses=campus) | Q(campuses__isnull=True))
            .distinct()
            .order_by("name")
        )
        context.update(paginate_context(self.request, promoters, 25))
        context["promoters"] = context["page_obj"]
        return context

    def post(self, request, *args, **kwargs):
        form = PromoterForm(request.POST)
        if form.is_valid():
            promoter = form.save()
            promoter.campuses.add(get_selected_campus(request))
            messages.success(request, f"Promotor «{promoter.name}» creado.")
            return redirect("promoter-list")
        return self.render_to_response(self.get_context_data(form=form))


class ActivityLogView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Bitácora de actividades de los usuarios; solo para administradores."""

    template_name = "management/activity_log.html"
    context_object_name = "logs"
    paginate_by = 50

    def test_func(self):
        return self.request.user.is_superuser

    def get_queryset(self):
        get = self.request.GET
        logs = ActivityLog.objects.select_related("user", "campus")
        username = get.get("user", "").strip()
        if username:
            logs = logs.filter(username__iexact=username)
        if get.get("action") in ActivityLog.Action.values:
            logs = logs.filter(action=get["action"])
        if get.get("campus", "").isdigit():
            logs = logs.filter(campus_id=int(get["campus"]))
        text = get.get("q", "").strip()
        if text:
            logs = logs.filter(Q(description__icontains=text) | Q(path__icontains=text))
        date_from = parse_date(get.get("date_from", ""))
        date_to = parse_date(get.get("date_to", ""))
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)
        if get.get("exclude_self"):
            logs = logs.exclude(user=self.request.user)
        return logs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        get = self.request.GET
        context["actions"] = ActivityLog.Action.choices
        context["campuses"] = Campus.objects.order_by("name")
        context["users_list"] = User.objects.order_by("username").values_list("username", flat=True)
        filter_names = ("user", "action", "campus", "q", "date_from", "date_to", "exclude_self")
        context["has_filters"] = any(get.get(name) for name in filter_names)
        params = get.copy()
        params.pop("page", None)
        context["pagination_query"] = params.urlencode()
        return context
