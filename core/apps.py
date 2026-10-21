from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from . import activity, lookups  # noqa: F401  (señales de auditoría y lookup __wild)
        from .dashboard_cache import connect_signals

        connect_signals()
