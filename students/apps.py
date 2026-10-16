from django.apps import AppConfig


class StudentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "students"

    def ready(self):
        from django.db.models.signals import post_save

        from core.models import Campus

        from .signals import create_unassigned_course

        post_save.connect(
            create_unassigned_course,
            sender=Campus,
            dispatch_uid="create_unassigned_course",
        )
