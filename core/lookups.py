from django.db.models import CharField, Lookup, TextField


def wildcard_pattern(text):
    """`*` = cualquier cantidad de caracteres, `?` = un carácter; el resto es literal."""
    escaped = str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escaped.replace("*", "%").replace("?", "_") + "%"


@CharField.register_lookup
@TextField.register_lookup
class WildcardContains(Lookup):
    """`campo__wild="ana*perez"`: como icontains, pero acepta los comodines `*` y `?`.

    Se puede encadenar con `unaccent` (campo__unaccent__wild) para ignorar tildes.
    """

    lookup_name = "wild"

    def get_prep_lookup(self):
        return wildcard_pattern(super().get_prep_lookup())

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"{lhs}::text ILIKE {rhs}", (*lhs_params, *rhs_params)
