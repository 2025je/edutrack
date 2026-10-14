from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Q, Prefetch, Count
from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView
from core.campus import SelectedCampusRequiredMixin, FeaturePermissionMixin, get_selected_campus
from .models import Student, Enrollment, Course
from .forms import StudentForm, EnrollmentForm


class CampusScopedMixin(FeaturePermissionMixin, SelectedCampusRequiredMixin, LoginRequiredMixin):
    permission_field = "can_manage_students"
    def campus_queryset(self, qs, field="campus"):
        campus = get_selected_campus(self.request)
        return qs.filter(**{field: campus})


class StudentListView(CampusScopedMixin, ListView):
    model = Student
    template_name = "students/student_list.html"
    context_object_name = "students"
    paginate_by = 25

    def get_queryset(self):
        qs = self.campus_queryset(Student.objects.select_related("campus"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(document_number__icontains=q))
        return qs


class StudentCreateView(CampusScopedMixin, CreateView):
    model = Student
    form_class = StudentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("student-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.campus = get_selected_campus(self.request)
        response = super().form_valid(form)
        messages.success(self.request, "Estudiante registrado correctamente.")
        return response


class EnrollmentListView(CampusScopedMixin, ListView):
    model = Enrollment
    template_name = "students/enrollment_list.html"
    context_object_name = "enrollments"
    paginate_by = 25

    def get_queryset(self):
        return self.campus_queryset(Enrollment.objects.select_related("campus", "student", "course", "promoter")).order_by("-created_at")


class EnrollmentCreateView(CampusScopedMixin, CreateView):
    model = Enrollment
    form_class = EnrollmentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("enrollment-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        campus = get_selected_campus(self.request)
        form.instance.campus = campus
        form.instance.enrollment_fee = form.cleaned_data["enrollment_fee"]
        form.instance.monthly_fee = form.cleaned_data["monthly_fee"]
        try:
            with transaction.atomic():
                self.object = form.save()
                from payments.models import Installment
                if self.object.enrollment_fee > 0:
                    Installment.objects.create(
                        enrollment=self.object, concept="Matrícula",
                        amount=self.object.enrollment_fee, due_date=self.object.course.start_date,
                    )
                if self.object.monthly_fee > 0:
                    Installment.objects.create(
                        enrollment=self.object,
                        concept=f"Mensualidad inicial ({self.object.course.start_date:%Y-%m})",
                        amount=self.object.monthly_fee, due_date=self.object.course.start_date,
                    )
        except IntegrityError:
            form.add_error("course", "Este estudiante ya está matriculado en este curso.")
            return self.form_invalid(form)
        messages.success(self.request, "Matrícula registrada y cuotas iniciales generadas.")
        return redirect(self.get_success_url())


class CourseStudentTablesView(CampusScopedMixin, ListView):
    """Muestra una tabla independiente por curso para la sede seleccionada."""
    model = Course
    template_name = "students/course_student_tables.html"
    context_object_name = "courses"

    def get_queryset(self):
        campus = get_selected_campus(self.request)
        enrollments = (
            Enrollment.objects.filter(campus=campus, active=True, student__active=True)
            .select_related("student", "course")
            .order_by("student__full_name")
        )
        qs = (
            Course.objects.filter(campus=campus, active=True)
            .annotate(student_count=Count("enrollments", filter=Q(enrollments__active=True)))
            .prefetch_related(Prefetch("enrollments", queryset=enrollments))
            .order_by("name", "schedule", "group")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(schedule__icontains=q) | Q(group__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["total_students"] = Enrollment.objects.filter(
            campus=get_selected_campus(self.request), active=True, student__active=True
        ).values("student_id").distinct().count()
        return context


class AvailableStudentsForCourseView(CampusScopedMixin, ListView):
    """Devuelve por AJAX los alumnos de la sede aún no inscritos al curso."""
    def get(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        course_id = request.GET.get("course_id")
        if not course_id:
            return JsonResponse({"students": []})
        course = Course.objects.filter(pk=course_id, campus=campus, active=True).first()
        if course is None:
            return JsonResponse({"students": []}, status=400)
        enrolled_ids = Enrollment.objects.filter(course=course).values_list("student_id", flat=True)
        students = Student.objects.filter(campus=campus, active=True).exclude(
            pk__in=enrolled_ids
        ).order_by("full_name").values("id", "full_name")
        return JsonResponse({"students": list(students)})
