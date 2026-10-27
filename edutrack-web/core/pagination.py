from django.core.paginator import Paginator


def paginate_context(request, queryset, per_page=25):
    """Devuelve el contexto que espera shared/pagination.html para vistas que no son ListView."""
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return {
        "page_obj": page_obj,
        "paginator": page_obj.paginator,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": params.urlencode(),
    }
