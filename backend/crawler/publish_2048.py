"""2048 地址发布页 → 当日可用论坛入口。

发布页（如 https://fby.tfzqs88.com/）本身不是 PHPWind，
「论坛今日地址」「免翻域名」里的链接才是当日 BBS / 跳转入口。
"""

from __future__ import annotations

import logging
import re
from typing import Callable
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

PUBLISH_HOST_PREFIXES = ("fby.",)
PUBLISH_HOST_HINTS = ("tfzqs", "js-bovey", "chinpol", "syhsyh", "quanjingzx")

# 只要这两个分区；影院 / 其它娱乐不要
FORUM_SECTION_TITLES = ("论坛今日地址", "免翻域名")
SKIP_SECTION_TITLES = ("影院今日地址", "其他娱乐", "其它娱乐")

A_HREF_RE = re.compile(
    r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>""",
    re.I,
)
SECTION_RE = re.compile(
    r"""<section\b[^>]*>(.*?)</section>""",
    re.I | re.S,
)
H2_RE = re.compile(r"""<h2\b[^>]*>(.*?)</h2>""", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html or "")).strip()


def is_2048_publish_url(url: str) -> bool:
    """是否像 2048 今日地址发布页（非 BBS 本体）。"""
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        p = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return False
    host = (p.netloc or "").lower().split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith(PUBLISH_HOST_PREFIXES):
        return True
    if any(h in host for h in PUBLISH_HOST_HINTS):
        return True
    path = (p.path or "/").rstrip("/") or "/"
    # 裸发布页根路径；带 /lt1.php 一类跳转不算发布页本体
    if path == "/" and host.startswith("fby."):
        return True
    return False


def _origin(url: str) -> str:
    p = urlparse(url if "://" in url else f"https://{url}")
    scheme = p.scheme or "https"
    netloc = p.netloc
    if not netloc:
        return ""
    return f"{scheme}://{netloc}/"


def parse_2048_publish_forum_links(html: str, base_url: str) -> list[str]:
    """从发布页 HTML 抽出论坛分区链接（相对路径会拼到 base_url）。"""
    cleaned = COMMENT_RE.sub("", html or "")
    base = (base_url or "").strip() or "https://fby.tfzqs88.com/"
    if not base.endswith("/"):
        base += "/"

    found: list[str] = []
    seen: set[str] = set()

    def _add(href: str) -> None:
        absu = urljoin(base, (href or "").strip())
        if not absu or absu.startswith(("javascript:", "mailto:", "#")):
            return
        key = absu.rstrip("/")
        if key in seen:
            return
        # 跳过仍指向发布页根（无意义）
        if is_2048_publish_url(absu) and urlparse(absu).path in ("", "/"):
            return
        seen.add(key)
        found.append(absu)

    sections = SECTION_RE.findall(cleaned)
    if sections:
        for block in sections:
            h2m = H2_RE.search(block)
            title = _strip_tags(h2m.group(1)) if h2m else ""
            if any(s in title for s in SKIP_SECTION_TITLES):
                continue
            if title and not any(s in title for s in FORUM_SECTION_TITLES):
                continue
            if not title:
                # 无标题时仅在全文回落路径使用
                continue
            for href in A_HREF_RE.findall(block):
                _add(href)
        if found:
            return found

    # 回落：无 section 结构时按链接文案过滤
    for m in re.finditer(
        r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
        cleaned,
        re.I | re.S,
    ):
        href, inner = m.group(1), _strip_tags(m.group(2))
        if any(x in inner for x in ("影院", "酒店", "直播", "客服", "监控", "漫画")):
            continue
        if any(x in inner for x in ("论坛", "免翻", "线路", "地址", "移动", "新域", "高速", "加密", "备用")):
            _add(href)
            continue
        low = href.lower()
        if "bbs." in low or any(x in low for x in ("/bbs", "/lt", "/418", "/bps")):
            _add(href)
    return found


def resolve_2048_jump_origin(
    url: str,
    *,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
    proxy: str = "",
    client: object | None = None,
) -> str:
    """跟随跳转，返回最终论坛 origin（失败则退回原 URL 的 origin/自身）。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    # 已是绝对 BBS 主机且非发布页跳转脚本：直接用 origin
    path = urlparse(raw if "://" in raw else f"https://{raw}").path.lower()
    if not is_2048_publish_url(raw) and not path.endswith(".php"):
        return _origin(raw) or raw

    close_client = False
    http = client
    if http is None:
        import httpx

        kwargs: dict = {
            "headers": headers
            or {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            },
            "timeout": timeout,
            "verify": False,
            "follow_redirects": True,
        }
        if proxy:
            kwargs["proxy"] = proxy
        http = httpx.Client(**kwargs)
        close_client = True
    try:
        r = http.get(raw)  # type: ignore[attr-defined]
        final = str(getattr(r, "url", raw) or raw)
        origin = _origin(final)
        if origin and not is_2048_publish_url(origin):
            return origin
        # 仍停在发布域：保留跳转 URL 交给浏览器过门
        return raw if raw.endswith("/") or ".php" in raw else (raw + "/")
    except Exception as exc:
        log.info("2048 jump resolve failed %s: %s", raw, exc)
        return _origin(raw) or raw
    finally:
        if close_client:
            try:
                http.close()  # type: ignore[attr-defined]
            except Exception:
                pass


def expand_2048_entry_urls(
    entry_urls: list[str],
    *,
    timeout: float = 8.0,
    headers: dict[str, str] | None = None,
    proxy: str = "",
    fetch_html: Callable[[str], str] | None = None,
    resolve_jumps: bool = False,
    max_publish_pages: int = 1,
    max_entries: int = 8,
) -> list[str]:
    """配置入口 → 可进站候选。

    默认只解第一个可用发布页，且不预跟跳转（交给浏览器过门），避免卡住调度。
    """
    hdrs = headers or {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    out: list[str] = []
    seen: set[str] = set()
    publish_ok = 0
    limit = max(1, int(max_entries or 8))

    def _push(u: str) -> bool:
        nonlocal out
        if len(out) >= limit:
            return False
        u = (u or "").strip()
        if not u:
            return True
        key = u.rstrip("/").lower()
        if key in seen:
            return True
        seen.add(key)
        out.append(u if u.endswith("/") or ".php" in urlparse(u).path.lower() else u + "/")
        return len(out) < limit

    import httpx

    client = httpx.Client(
        headers=hdrs,
        timeout=timeout,
        verify=False,
        follow_redirects=True,
        **({"proxy": proxy} if proxy else {}),
    )
    try:
        for raw in entry_urls or []:
            if len(out) >= limit:
                break
            url = (raw or "").strip()
            if not url:
                continue
            if not is_2048_publish_url(url):
                _push(url)
                continue
            if publish_ok >= max(1, int(max_publish_pages or 1)):
                # 已有发布页展开成功；其余发布页仅作备用，不再全量爬（防卡住）
                continue
            try:
                if fetch_html is not None:
                    html = fetch_html(url)
                else:
                    resp = client.get(url)
                    html = resp.text
                    url = str(resp.url)
            except Exception as exc:
                log.warning("2048 publish fetch failed %s: %s", url, exc)
                continue

            links = parse_2048_publish_forum_links(html, url)
            if not links:
                log.warning("2048 publish page has no forum links: %s", url)
                continue

            publish_ok += 1
            log.info("2048 publish %s → %d forum link(s)", url, len(links))
            for link in links:
                if resolve_jumps:
                    resolved = resolve_2048_jump_origin(
                        link,
                        timeout=min(timeout, 6.0),
                        headers=hdrs,
                        proxy=proxy,
                        client=client,
                    )
                    if not _push(resolved):
                        break
                else:
                    if not _push(link):
                        break
    finally:
        client.close()

    if out:
        return _prefer_direct_bbs(out)
    # 全失败：退回原始入口，让 bootstrap 自己 failover
    return [u.strip() for u in (entry_urls or []) if (u or "").strip()][:limit]


def _prefer_direct_bbs(urls: list[str]) -> list[str]:
    """bbs. 直链优先，发布页跳转脚本靠后，降低首试失败率。"""

    def rank(u: str) -> tuple[int, str]:
        try:
            p = urlparse(u)
        except Exception:
            return (9, u)
        host = (p.netloc or "").lower()
        path = (p.path or "").lower()
        host_only = host.split(":", 1)[0]
        if host_only.startswith("bbs."):
            return (0, u)
        if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host_only):
            return (3, u)
        if path.endswith(".php") and (
            host_only.startswith("fby.") or any(h in host_only for h in PUBLISH_HOST_HINTS)
        ):
            return (2, u)
        return (1, u)

    return sorted(urls, key=rank)
