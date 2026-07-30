"""补写 resource_sources.description 中缺失的大小行。

针对与 tid=3659150 同类：库内 size/标题已有容量，但描述缺【资源大小】等
（装饰括号【4.92GB/…】曾被 clip 切空）。不重爬，只改描述。

Usage:
  python scripts/repair_missing_size_desc.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.resource_db import connect_resource
from parsers.content import description_profile_for_board
from parsers.magnet import parse_capacity_bytes, unwrap_decorative_capacity_value
from parsers.thread_gates import close_trailing_capacity_bracket

_SIZE_LINE_RE = re.compile(
    r"【\s*(?:资源大小|資源大小|影片大小|影片容量|文件大小|檔案大小)\s*】",
    re.I,
)
_BRACKET_CHUNK_RE = re.compile(r"[【［\[]([^】］\]]{1,48})[】］\]]")
_OPEN_CAP_TAIL_RE = re.compile(r"[【［\[]([^【［\[】］\]]*)$")


def _size_key_for_board(board_fid: str | None) -> str:
    profile = description_profile_for_board(board_fid)
    labels = tuple(profile.get("labels") or ())
    for cand in (
        "资源大小",
        "影片大小",
        "影片容量",
        "文件大小",
        "檔案大小",
    ):
        if cand in labels:
            return cand
    return "资源大小"


def size_label_from_title(title: str) -> str:
    """从标题容量装饰段抽出可读标签（优先完整【…GB/…配额】）。"""
    t = close_trailing_capacity_bracket(title or "")
    best = ""
    best_n = 0
    for inner in _BRACKET_CHUNK_RE.findall(t):
        n = parse_capacity_bytes(inner)
        if n > best_n:
            best_n = n
            best = unwrap_decorative_capacity_value(f"【{inner}】") or inner.strip()
    if best:
        return best
    # 未闭合尾段（close 未认完）
    m = _OPEN_CAP_TAIL_RE.search((title or "").rstrip())
    if m:
        inner = (m.group(1) or "").strip()
        if parse_capacity_bytes(inner) > 0:
            return unwrap_decorative_capacity_value(f"【{inner}】") or inner
    # 全文扫容量 token 拼最短可读
    n = parse_capacity_bytes(t)
    if n <= 0:
        return ""
    m2 = re.search(
        r"(\d+(?:\.\d+)?\s*(?:TB|GB|MB|KB|[TGMK])B?(?:\s*/\s*\d+\s*[VvPp])?(?:\s*/\s*\d+\s*配额)?)",
        t,
        re.I,
    )
    if m2:
        return re.sub(r"\s+", "", m2.group(1))
    return ""


def format_bytes_label(n: int) -> str:
    if n <= 0:
        return ""
    for unit, div in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2)):
        if n >= div:
            v = n / div
            if abs(v - round(v)) < 1e-6:
                return f"{int(round(v))}{unit}"
            return f"{v:.2f}".rstrip("0").rstrip(".") + unit
    return f"{n}B"


def insert_size_into_description(
    desc: str,
    *,
    size_key: str,
    size_label: str,
) -> str:
    if not size_label or _SIZE_LINE_RE.search(desc or ""):
        return desc or ""
    line = f"【{size_key}】：{size_label}"
    lines = [ln for ln in (desc or "").split("\n")]
    # 插在 profile 常见前序字段之后
    after_keys = (
        "资源类型",
        "資源類型",
        "资源数量",
        "资源名称",
        "資源名稱",
        "影片名称",
        "影片名稱",
        "出演女优",
    )
    insert_at = 0
    for i, ln in enumerate(lines):
        for k in after_keys:
            if re.match(rf"【\s*{re.escape(k)}\s*】", ln or ""):
                insert_at = i + 1
                break
    lines.insert(insert_at, line)
    return "\n".join(ln for ln in lines if ln is not None).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    c = connect_resource()
    cur = c.cursor()
    cur.execute(
        """
        SELECT s.id, s.hash, s.board_fid, s.title, s.description, r.size
        FROM resource_sources s
        LEFT JOIN ed2k_resources r ON r.hash = s.hash
        WHERE coalesce(s.description, '') <> ''
        ORDER BY s.id
        """
    )
    updated = 0
    skipped = 0
    for rid, _h, board, title, desc, size in cur.fetchall():
        if _SIZE_LINE_RE.search(desc or ""):
            skipped += 1
            continue
        label = size_label_from_title(title or "")
        if not label:
            label = format_bytes_label(int(size or 0))
        if not label:
            print(f"skip id={rid}: no size label")
            continue
        # 标题无容量且库 size=0 才跳过；有字节也可补
        if parse_capacity_bytes(title or "") <= 0 and int(size or 0) <= 0:
            continue
        key = _size_key_for_board(board)
        new_desc = insert_size_into_description(
            desc or "", size_key=key, size_label=label
        )
        if new_desc == (desc or "").strip():
            continue
        print(f"id={rid} +【{key}】：{label}")
        if not args.dry_run:
            cur.execute(
                "UPDATE resource_sources SET description=%s WHERE id=%s",
                (new_desc, rid),
            )
        updated += 1
    if not args.dry_run:
        c.commit()
    c.close()
    print(f"done updated={updated} already_had_size_line≈{skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
