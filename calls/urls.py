from django.urls import path

from .views import (
    CallAssignmentView,
    CallNoteAllListView,
    CallNoteCreateView,
    CallNoteDeleteView,
    CallNoteListView,
    CallNoteUpdateView,
    CallQuickNoteView,
    CallQueueStatusView,
    CallQueueView,
    CallReportView,
    CallStudentListView,
    WhatsAppMarkView,
    WhatsAppOpenView,
    WhatsAppTemplateView,
)

urlpatterns = [
    path("cola/", CallQueueView.as_view(), name="calls-queue"),
    path("cola/estado/", CallQueueStatusView.as_view(), name="calls-queue-status"),
    path("historial/<int:pk>/editar/", CallNoteUpdateView.as_view(), name="calls-note-update"),
    path("historial/<int:pk>/eliminar/", CallNoteDeleteView.as_view(), name="calls-note-delete"),
    path("historial/", CallNoteAllListView.as_view(), name="calls-notes-all"),
    path("alumnos/<int:student_id>/historial/", CallNoteListView.as_view(), name="calls-notes"),
    path(
        "alumnos/<int:student_id>/historial/nueva/",
        CallNoteCreateView.as_view(),
        name="calls-note-create",
    ),
    path(
        "alumnos/<int:student_id>/registro-rapido/",
        CallQuickNoteView.as_view(),
        name="calls-quick-note",
    ),
    path("plantilla/", WhatsAppTemplateView.as_view(), name="calls-template"),
    path(
        "alumnos/<int:student_id>/whatsapp/",
        WhatsAppOpenView.as_view(),
        name="calls-whatsapp-open",
    ),
    path(
        "alumnos/<int:student_id>/whatsapp/marcar/",
        WhatsAppMarkView.as_view(),
        name="calls-whatsapp-mark",
    ),
    path("asignaciones/", CallAssignmentView.as_view(), name="calls-assignments"),
    path("reportes/", CallReportView.as_view(), name="calls-report"),
    path("alumnos/", CallStudentListView.as_view(), name="calls-students"),
]
