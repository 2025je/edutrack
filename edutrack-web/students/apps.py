from django.apps import AppConfig


class StudentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "students"

    def ready(self):
        from django.db.models.signals import post_save

        from core.models import Campus

        from .signals import create_campus_defaults

        post_save.connect(
            create_campus_defaults,
            sender=Campus,
            dispatch_uid="create_campus_defaults",
        )
