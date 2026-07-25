"""2048 / 人人为我论坛（PHPWind）站点适配。"""

from __future__ import annotations

from pathlib import Path

from crawler.sites.base import ForumSiteAdapter, domains_from_entry, site_root_from_entry
from parsers.boards import BoardPolicy
from parsers.boards_2048 import (
    BOARD_POLICIES_2048,
    default_board_order_2048,
    expand_board_keys_2048,
    get_board_policy_2048,
)

COOKIE_FILE_2048 = Path(__file__).resolve().parent.parent.parent / "data" / "cookies_2048.json"
DEFAULT_ENTRY = "https://ut2gw5.xc6ym5.com/"


class Forum2048Adapter:
    forum_id = "2048"
    engine = "phpwind"

    def cookie_file(self) -> Path:
        return COOKIE_FILE_2048

    def cookie_domains(self, entry_url: str = "") -> tuple[str, ...]:
        derived = domains_from_entry(entry_url or DEFAULT_ENTRY)
        return derived or domains_from_entry(DEFAULT_ENTRY)

    def board_policies(self) -> dict[str, BoardPolicy]:
        return BOARD_POLICIES_2048

    def default_board_order(self) -> list[str]:
        return default_board_order_2048()

    def expand_board_keys(self, keys: list[str] | None) -> list[str]:
        return expand_board_keys_2048(keys)

    def get_board_policy(self, fid_or_key: int | str) -> BoardPolicy:
        return get_board_policy_2048(fid_or_key)

    def build_list_url(self, root: str, board_key: str | int, page: int = 1) -> str:
        pol = self.get_board_policy(board_key)
        base = site_root_from_entry(root or DEFAULT_ENTRY, fallback=DEFAULT_ENTRY)
        page = max(1, int(page or 1))
        if page <= 1:
            return f"{base}thread.php?fid={pol.fid}"
        return f"{base}thread.php?fid={pol.fid}&page={page}"

    def build_thread_url(self, root: str, tid: int | str) -> str:
        base = site_root_from_entry(root or DEFAULT_ENTRY, fallback=DEFAULT_ENTRY)
        return f"{base}read.php?tid={int(tid)}"

    def bootstrap_probe_url(self, root: str) -> str:
        base = site_root_from_entry(root or DEFAULT_ENTRY, fallback=DEFAULT_ENTRY)
        # 新片速递：过年龄门后应能看到列表
        return f"{base}thread.php?fid=2"


ADAPTER: ForumSiteAdapter = Forum2048Adapter()
