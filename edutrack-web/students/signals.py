from .models import ensure_default_promoters, ensure_default_schedules


def create_campus_defaults(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        ensure_default_schedules(instance)
        ensure_default_promoters(instance)
