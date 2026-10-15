from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from students.models import Course, Promoter, Schedule

from .forms import CourseForm, PromoterForm, ScheduleForm


class CatalogManagerMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin, LoginRequiredMixin):
    permission_field = "can_manage_promoters"


class CourseCreateView(CatalogManagerMixin, TemplateView):
    template_name = "catalog/courses.html"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        campus = get_selected_campus(self.request)
        context["form"] = form or CourseForm(
            campus=campus, initial={"schedule": self.request.GET.get("schedule")}
        )
        context["courses"] = Course.objects.filter(campus=campus)
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


class ScheduleCreateView(CatalogManagerMixin, TemplateView):
    template_name = "catalog/schedule_form.html"

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
    template_name = "catalog/promoters.html"

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
