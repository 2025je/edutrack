from .campus import available_campuses, get_selected_campus


def selected_campus_context(request):
    campus = None
    campuses = []
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        campus = get_selected_campus(request)
        campuses = list(available_campuses(request.user))
    return {"selected_campus": campus, "available_campuses": campuses}
