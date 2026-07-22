"""115 网盘分享页（分享码/访问码）解析。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs

# https://115cdn.com/s/xxx?password=1122  /  https://115.com/s/xxx
RE_115_SHARE_URL = re.compile(
    r"(?:https?://)?(?:www\.)?(?P<host>115cdn\.com|115\.com)/s/(?P<sid>[A-Za-z0-9]+)"
    r"(?P<query>\?[^\s<>\"'#]*)?",
    re.I,
)

# 115访问码：1122 / 访问码：xxxx / 分享码：xxxx（避免误吃百度「提取码」优先用 115 前缀）
RE_115_CODE_LABELED = re.compile(
    r"(?:115\s*)?(?:访问码|分享码)\s*[:：]\s*([A-Za-z0-9]{3,12})",
    re.I,
)
RE_GENERIC_CODE = re.compile(
    r"(?:访问码|分享码|提取码)\s*[:：]\s*([A-Za-z0-9]{3,12})",
    re.I,
)


@dataclass(slots=True)
class Share115Link:
    share_id: str
    host: str
    password: str
    url: str  # 规范链（可带 password 查询）
    hash: str
    filename: str


def share115_hash(share_id: str, host: str = "115cdn.com") -> str:
    raw = f"115share:{(host or '115cdn.com').lower()}/{(share_id or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32].upper()


def build_share115_url(host: str, share_id: str, password: str = "") -> str:
    h = (host or "115cdn.com").lower()
    if h not in {"115.com", "115cdn.com"}:
        h = "115cdn.com"
    base = f"https://{h}/s/{share_id}"
    pwd = (password or "").strip()
    if pwd:
        return f"{base}?password={pwd}"
    return base


def _password_from_query(query: str) -> str:
    if not query:
        return ""
    q = query[1:] if query.startswith("?") else query
    params = parse_qs(q, keep_blank_values=False)
    for key in ("password", "pwd", "passwd"):
        vals = params.get(key) or params.get(key.upper())
        if vals and vals[0]:
            return str(vals[0]).strip()
    return ""


def _pick_access_code(text: str, *, prefer_near: str = "") -> str:
    """从正文取访问码；优先带 115 标签的，其次通用。"""
    blob = text or ""
    if prefer_near:
        window = prefer_near
        m = RE_115_CODE_LABELED.search(window) or RE_GENERIC_CODE.search(window)
        if m:
            return m.group(1).strip()
    m = RE_115_CODE_LABELED.search(blob)
    if m:
        return m.group(1).strip()
    # 仅当文中有 115 分享上下文时才用通用「提取码」，避免误用百度码
    if RE_115_SHARE_URL.search(blob) or re.search(r"115", blob, re.I):
        # 115 段落附近的访问码已在 labeled 里；通用提取码可能是百度的，跳过
        pass
    return ""


def parse_115_share_text(text: str, *, title: str = "") -> list[Share115Link]:
    """从语料抽出 115 分享页链接 + 访问码。"""
    blob = text or ""
    if not blob:
        return []

    results: list[Share115Link] = []
    seen: set[str] = set()
    fallback_code = _pick_access_code(blob)

    for m in RE_115_SHARE_URL.finditer(blob):
        host = (m.group("host") or "115cdn.com").lower()
        share_id = (m.group("sid") or "").strip()
        if not share_id:
            continue
        key = f"{host}/{share_id}".lower()
        if key in seen:
            continue
        seen.add(key)

        pwd = _password_from_query(m.group("query") or "")
        if not pwd:
            # 链接前后约 200 字找访问码
            start = max(0, m.start() - 80)
            end = min(len(blob), m.end() + 200)
            pwd = _pick_access_code(blob, prefer_near=blob[start:end]) or fallback_code

        url = build_share115_url(host, share_id, pwd)
        filename = (title or "").strip() or f"115分享-{share_id}"
        results.append(
            Share115Link(
                share_id=share_id,
                host=host,
                password=pwd,
                url=url,
                hash=share115_hash(share_id, host),
                filename=filename[:240],
            )
        )

    return results


def pick_primary_115_share(links: list[Share115Link]) -> Share115Link | None:
    if not links:
        return None
    # 优先带访问码的
    with_pwd = [x for x in links if x.password]
    pool = with_pwd or links
    return pool[0]
