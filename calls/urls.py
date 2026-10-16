from django.urls import path

from .views import (
    CallNoteAllListView,
    CallNoteCreateView,
    CallNoteDeleteView,
    CallNoteListView,
    CallNoteUpdateView,
    CallStudentListView,
    WhatsAppTemplateView,
)

urlpatterns = [
    path("historial/<int:pk>/editar/", CallNoteUpdateView.as_view(), name="calls-note-update"),
    path("historial/<int:pk>/eliminar/", CallNoteDeleteView.as_view(), name="calls-note-delete"),
    path("historial/", CallNoteAllListView.as_view(), name="calls-notes-all"),
    path("alumnos/<int:student_id>/historial/", CallNoteListView.as_view(), name="calls-notes"),
    path(
        "alumnos/<int:student_id>/historial/nueva/",
        CallNoteCreateView.as_view(),
        name="calls-note-create",
    ),
    path("plantilla/", WhatsAppTemplateView.as_view(), name="calls-template"),
    path("alumnos/", CallStudentListView.as_view(), name="calls-students"),
]
