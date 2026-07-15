"""ED2K link parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

ED2K_RE = re.compile(
    r"ed2k://\|file\|([^\|]+)\|(\d+)\|([A-Fa-f0-9]{32})\|",
    re.IGNORECASE,
)

ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z", ".cbz", ".cbr")


@dataclass(slots=True)
class Ed2kLink:
    filename: str
    size: int
    hash: str
    link: str


def build_ed2k_link(filename: str, size: int, file_hash: str) -> str:
    return f"ed2k://|file|{filename}|{size}|{file_hash.upper()}|/"


def build_search_string(
    filename: str,
    title: str = "",
    description: str = "",
    extract_password: str = "",
) -> str:
    parts: list[str] = []
    for item in (filename, title, description, extract_password):
        text = (item or "").strip()
        if text and text not in parts:
            parts.append(text)
    return " ".join(parts)


def parse_ed2k_text(text: str) -> list[Ed2kLink]:
    results: list[Ed2kLink] = []
    seen: set[str] = set()

    for match in ED2K_RE.finditer(text or ""):
        filename = match.group(1).strip()
        size = int(match.group(2))
        file_hash = match.group(3).upper()
        if file_hash in seen:
            continue
        seen.add(file_hash)
        results.append(
            Ed2kLink(
                filename=filename,
                size=size,
                hash=file_hash,
                link=build_ed2k_link(filename, size, file_hash),
            )
        )

    return results


def pick_primary_ed2k(links: list[Ed2kLink]) -> Ed2kLink | None:
    """Prefer archives; otherwise largest size."""
    if not links:
        return None
    archives = [link for link in links if link.filename.lower().endswith(ARCHIVE_EXTENSIONS)]
    if archives:
        return max(archives, key=lambda item: item.size)
    return max(links, key=lambda item: item.size)
