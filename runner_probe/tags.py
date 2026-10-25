"""Tag normalization for the isolated runner capability fixture."""


def normalize_tags(values):
    """Return normalized tags without mutating the input.

    The input must be a list of strings. Every tag is stripped of surrounding
    whitespace, Unicode casefolded and deduplicated in first-seen order. Blank
    tags are rejected because they carry no meaning.
    """
    if not isinstance(values, list):
        raise TypeError("tags must be a list of strings")

    normalized = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("each tag must be a string")
        tag = value.strip().casefold()
        if not tag:
            raise ValueError("tags must not be blank")
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)
    return normalized
