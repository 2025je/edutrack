from django.db.models import Q


def filter_students(queryset, query, with_fichas=False):
    """Cada palabra debe coincidir con nombre (sin tildes ni orden), DNI, teléfono o código de ficha."""
    from .models import Ficha

    for word in query.split()[:6]:
        condition = (
            Q(full_name__unaccent__icontains=word)
            | Q(document_number__icontains=word)
            | Q(phone__icontains=word)
        )
        if with_fichas and word.isdigit() and len(word) <= 9:
            condition |= Q(
                pk__in=Ficha.objects.filter(code=int(word)).values("enrollment__student_id")
            )
        queryset = queryset.filter(condition)
    return queryset
