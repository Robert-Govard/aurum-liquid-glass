"""Shared text-formatting helpers."""


def capitalize_first_letter(value: str) -> str:
    """Uppercase the first character, leaving the rest of the string untouched.

    Unlike str.capitalize()/str.title(), this never lowercases the rest of the
    string — "iPhone 15" stays "iPhone 15", not "Iphone 15".
    """
    if not value:
        return value
    return value[0].upper() + value[1:]
