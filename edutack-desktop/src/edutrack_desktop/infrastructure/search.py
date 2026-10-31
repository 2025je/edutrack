import unicodedata


def normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    folded = unicodedata.normalize("NFKD", decomposed.casefold())
    return "".join(
        character
        for character in folded
        if not unicodedata.combining(character)
    )
