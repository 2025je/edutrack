from .models import ensure_default_promoters, ensure_default_schedules, ensure_unassigned_course


def create_unassigned_course(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        ensure_default_schedules(instance)
        ensure_unassigned_course(instance)
        ensure_default_promoters(instance)
