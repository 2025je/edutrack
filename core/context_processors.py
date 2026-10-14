from .campus import get_selected_campus


def selected_campus_context(request):
    campus = None
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        campus = get_selected_campus(request)
    return {"selected_campus": campus}
