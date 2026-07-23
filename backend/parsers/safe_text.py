"""Strip characters PostgreSQL text/varchar cannot store."""

from __future__ import annotations


def strip_nul(value: str | None) -> str:
    """Remove NUL (0x00); psycopg/Postgres reject them in string literals."""
    if not value:
        return ""
    if "\x00" not in value:
        return value
    return value.replace("\x00", "")


def strip_nul_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for item in values:
        cleaned = strip_nul(item)
        if cleaned:
            out.append(cleaned)
    return out
