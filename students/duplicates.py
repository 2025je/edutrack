import unicodedata

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from calls.models import CallNote
from core.activity import record
from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import ActivityLog

from .models import Enrollment, Student


def name_key(full_name):
    """Nombre sin tildes ni mayúsculas y con las palabras ordenadas ("PÉREZ JUAN" = "JUAN PEREZ")."""
    plain = unicodedata.normalize("NFKD", full_name)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join(sorted(plain.upper().split()))


def find_duplicate_groups(campus):
    groups = {}
    for student in Student.objects.filter(campus=campus, active=True).order_by("created_at", "pk"):
        groups.setdefault(name_key(student.full_name), []).append(student)
    return [group for group in groups.values() if len(group) > 1]


@transaction.atomic
def merge_students(keep, duplicate):
    """Pasa matrículas y llamadas del duplicado al estudiante principal y lo da de baja."""
    moved = Enrollment.objects.filter(student=duplicate).update(student=keep)
    CallNote.objects.filter(student=duplicate).update(student=keep)
    if not keep.phone and duplicate.phone:
        keep.phone = duplicate.phone
    if not keep.document_number and duplicate.document_number:
        keep.document_number = duplicate.document_number
    keep.save()
    duplicate.active = False
    duplicate.save(update_fields=["active"])
    return moved


class StudentDuplicatesView(FeaturePermissionMixin, SelectedCampusRequiredMixin, TemplateView):
    """Detecta estudiantes repetidos de la sede y permite fusionarlos."""

    template_name = "students/duplicates.html"
    required_permission = ("students.change_student", "core.deactivate_student")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = find_duplicate_groups(get_selected_campus(self.request))
        return context

    def post(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        keep = get_object_or_404(Student, pk=request.POST.get("keep"), campus=campus, active=True)
        duplicate = get_object_or_404(
            Student, pk=request.POST.get("duplicate"), campus=campus, active=True
        )
        if keep.pk == duplicate.pk or name_key(keep.full_name) != name_key(duplicate.full_name):
            messages.error(request, "Solo se pueden fusionar estudiantes con el mismo nombre.")
            return redirect("student-duplicates")
        moved = merge_students(keep, duplicate)
        record(
            request,
            ActivityLog.Action.UPDATE,
            f"Fusionó al estudiante {duplicate.pk} en {keep.pk} ({moved} matrículas)",
            object_type="student",
            object_id=keep.pk,
        )
        messages.success(
            request,
            f"Se fusionó «{duplicate.full_name}» en «{keep.full_name}» ({moved} matrículas).",
        )
        return redirect("student-duplicates")
