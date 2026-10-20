from .campus import available_campuses, get_selected_campus
from .onboarding import build_guide


def selected_campus_context(request):
    campus = None
    campuses = []
    guide = None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        campus = get_selected_campus(request)
        campuses = list(available_campuses(user))
        guide = build_guide(
            user, pending=user.onboarding_completed_at is None and campus is not None
        )
    return {"selected_campus": campus, "available_campuses": campuses, "onboarding": guide}
