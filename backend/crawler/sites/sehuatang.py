"""色花堂（Discuz）站点适配。"""

from __future__ import annotations

from pathlib import Path

from crawler.list_urls import build_list_url, site_root
from crawler.session import BASE_URL, COOKIE_DOMAINS, COOKIE_FILE
from crawler.sites.base import ForumSiteAdapter, domains_from_entry
from parsers.boards import (
    BOARD_POLICIES,
    BoardPolicy,
    default_board_order,
    expand_legacy_board_keys,
    get_board_policy,
)


class SehuatangAdapter:
    forum_id = "sehuatang"
    engine = "discuz"

    def cookie_file(self) -> Path:
        return COOKIE_FILE

    def cookie_domains(self, entry_url: str = "") -> tuple[str, ...]:
        derived = domains_from_entry(entry_url)
        if derived:
            # 合并官方域，避免 failover 时丢 cookie
            merged = list(dict.fromkeys([*COOKIE_DOMAINS, *derived]))
            return tuple(merged)
        return COOKIE_DOMAINS

    def board_policies(self) -> dict[str, BoardPolicy]:
        return BOARD_POLICIES

    def default_board_order(self) -> list[str]:
        return default_board_order()

    def expand_board_keys(self, keys: list[str] | None) -> list[str]:
        return expand_legacy_board_keys([str(x) for x in (keys or [])])

    def get_board_policy(self, fid_or_key: int | str) -> BoardPolicy:
        return get_board_policy(fid_or_key)

    def build_list_url(self, root: str, board_key: str | int, page: int = 1) -> str:
        pol = self.get_board_policy(board_key)
        return build_list_url(
            root or BASE_URL,
            pol.fid,
            page,
            typeid=pol.list_typeid,
            hot=False,
        )

    def build_thread_url(self, root: str, tid: int | str) -> str:
        base = site_root(root or BASE_URL)
        return f"{base}thread-{int(tid)}-1-1.html"

    def bootstrap_probe_url(self, root: str) -> str:
        base = site_root(root or BASE_URL)
        return f"{base}forum-2-1.html"


ADAPTER: ForumSiteAdapter = SehuatangAdapter()
