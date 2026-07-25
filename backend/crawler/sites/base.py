"""Forum site adapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from parsers.boards import BoardPolicy


class ForumSiteAdapter(Protocol):
    forum_id: str
    engine: str  # discuz | phpwind

    def cookie_file(self) -> Path: ...

    def cookie_domains(self, entry_url: str = "") -> tuple[str, ...]: ...

    def board_policies(self) -> dict[str, BoardPolicy]: ...

    def default_board_order(self) -> list[str]: ...

    def expand_board_keys(self, keys: list[str] | None) -> list[str]: ...

    def get_board_policy(self, fid_or_key: int | str) -> BoardPolicy: ...

    def build_list_url(self, root: str, board_key: str | int, page: int = 1) -> str: ...

    def build_thread_url(self, root: str, tid: int | str) -> str: ...

    def bootstrap_probe_url(self, root: str) -> str: ...


def domains_from_entry(entry_url: str) -> tuple[str, ...]:
    """从入口 URL 推导 Playwright cookie domain（含裸域与带点前缀）。"""
    raw = (entry_url or "").strip()
    if not raw:
        return ()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        return ()
    if not host:
        return ()
    # IP:port host → 仅主机名
    if host.replace(".", "").isdigit():
        return (host,)
    dotted = host if host.startswith(".") else f".{host}"
    if dotted == f".{host}":
        return (host, dotted)
    return (host, dotted)


def site_root_from_entry(entry_url: str, *, fallback: str = "https://www.sehuatang.net/") -> str:
    raw = (entry_url or "").strip() or fallback
    if "://" not in raw:
        raw = "https://" + raw
    p = urlparse(raw)
    if not p.netloc:
        return fallback if fallback.endswith("/") else fallback + "/"
    return f"{p.scheme}://{p.netloc}/"
