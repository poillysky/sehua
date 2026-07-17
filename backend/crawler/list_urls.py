"""Board list URL builders — 统一按发帖时间（orderby=dateline）排序。"""

from __future__ import annotations

from crawler.session import BASE_URL
from parsers.boards import BoardPolicy, get_board_policy


def site_root(entry_url: str = "") -> str:
    raw = (entry_url or BASE_URL).strip() or BASE_URL
    if "://" not in raw:
        raw = "https://" + raw
    if "forum.php" in raw or raw.rstrip("/").endswith(".html"):
        from urllib.parse import urlparse

        p = urlparse(raw)
        return f"{p.scheme}://{p.netloc}/"
    if not raw.endswith("/"):
        raw += "/"
    return raw


def build_list_url(
    root: str,
    board_fid: int | str,
    page: int = 1,
    *,
    typeid: str | None = None,
    hot: bool = False,
) -> str:
    """统一发帖时间序：orderby=dateline（不再走热榜 heats）。

    hot 参数保留兼容签名，忽略；全部板用发帖时间筛选。
    """
    del hot
    base = site_root(root)
    fid = str(board_fid).strip()
    page = max(1, int(page or 1))
    if typeid:
        return (
            f"{base}forum.php?mod=forumdisplay&fid={fid}"
            f"&filter=typeid&typeid={typeid}&orderby=dateline&page={page}"
        )
    return (
        f"{base}forum.php?mod=forumdisplay&fid={fid}"
        f"&filter=author&orderby=dateline&page={page}"
    )


def list_url_for_board(
    board_fid: int | str,
    page: int = 1,
    *,
    root: str = "",
    policy: BoardPolicy | None = None,
) -> str:
    """board_fid 可为纯 fid 或爬取单位 key（如 95:716）。"""
    pol = policy or get_board_policy(board_fid)
    return build_list_url(
        root or BASE_URL,
        pol.fid,
        page,
        typeid=pol.list_typeid,
        hot=False,
    )


def pages_to_scan(
    *,
    pages_per_board: int,
    min_thread_age_days: int = 0,
    last_list_page: int = 0,
) -> list[int]:
    """发帖时间序向前推进；有游标时从结束页重读（含），不 +1，避免漏帖。

    注：实际列表扫描见 workers.list_scan（另加每轮必读第 1 页）。
    """
    del min_thread_age_days  # 精确龄期在列表解析后按 posted_at 过滤
    n = max(1, int(pages_per_board or 1))
    last = max(int(last_list_page or 0), 0)
    if last <= 0:
        return list(range(1, 1 + n))
    # 含上次结束页：last=5 → [5, 6, ...]
    start = last if last >= 1 else 1
    return list(range(start, start + n))


def resolve_page_cap(pages_per_board: int, max_list_pages: int) -> int:
    """深扫每轮页数配额。跨轮从游标续扫直到板底。

    - pages_per_board：本轮翻页上限（至少 1）
    - max_list_pages > 0：本轮配额再与之取 min（页码硬顶仍由调用方 _page_hard_limit 管）
    """
    per = max(1, int(pages_per_board or 1))
    global_cap = int(max_list_pages or 0)
    if global_cap > 0:
        return min(per, global_cap)
    return per
