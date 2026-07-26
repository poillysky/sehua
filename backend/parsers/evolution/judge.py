"""Judge title / sub-filename / preview accuracy for one parsed thread."""
from __future__ import annotations

from typing import Any


_FN_POLLUTE = (
    "| 最新合集",
    "｜最新合集",
    "【目录树】",
    "【是否有水印】",
    "【文件类型】",
    "【档案格式】",
    "【注意事項】",
    "【注意事项】",
    "购买本帖",
    " 导演:",
    " 主演:",
    " 导演：",
    " 主演：",
)


def judge_parsed(
    *,
    title: str,
    assets: list[Any],
    title_spans: int = 0,
) -> dict[str, Any]:
    """Return {ok, issues, metrics}. assets: DualParseResult.assets-like."""
    fns = [(getattr(a, "filename", None) or "").strip() for a in assets]
    previews = [tuple(getattr(a, "preview_images", None) or []) for a in assets]
    uniq_fn = len({f for f in fns if f})
    prev_sets = {p for p in previews if p}
    first_imgs = [(p[0] if p else "") for p in previews]
    adj_same = sum(
        1
        for i in range(len(first_imgs) - 1)
        if first_imgs[i] and first_imgs[i] == first_imgs[i + 1]
    )
    n = len(assets)
    issues: list[str] = []

    t = title or ""
    if " | " in t or t.rstrip().endswith("最新合集"):
        issues.append("title_suffix")
    if any(x in t for x in ("| 最新合集", "｜最新合集")):
        issues.append("title_board_suffix")

    # 无解析出的资源：对进化验收一律不算通过（购买隐藏/附件未拉等）
    if n == 0:
        issues.append("empty_assets")

    if any(any(x in f for x in _FN_POLLUTE) for f in fns):
        issues.append("fn_polluted")
    if any(len(f) >= 240 for f in fns):
        issues.append("fn_overlong")

    if n >= 5 and uniq_fn <= 1:
        issues.append("identical_names")
    if n >= 2 and len(prev_sets) <= 1 and any(previews):
        # single shared non-empty preview set across multi assets
        if len({p for p in previews}) <= 1:
            issues.append("shared_preview")
    if n >= 5 and adj_same > n // 3:
        issues.append(f"adj_same_img:{adj_same}")
    if n >= 5 and sum(1 for p in previews if not p) > n // 2:
        issues.append("many_empty_preview")
    if title_spans and n >= 2 and uniq_fn < max(2, title_spans // 2):
        issues.append("spans_but_weak_names")

    # multi: every real asset should not just copy thread title
    if n >= 5 and t:
        same_as_title = sum(1 for f in fns if f and f == t)
        if same_as_title >= max(3, n // 2):
            issues.append("filename_copies_title")
        if any(f.startswith(t) and len(f) > len(t) + 3 for f in fns if f):
            issues.append("fn_title_prefix")

    return {
        "ok": not issues,
        "issues": issues,
        "metrics": {
            "n": n,
            "uniq_fn": uniq_fn,
            "prev_sets": len(prev_sets),
            "adj_same": adj_same,
            "title_spans": title_spans,
            "fn0": (fns[0][:80] if fns else ""),
            "fn1": (fns[1][:80] if len(fns) > 1 else ""),
            "title": (t[:100] if t else ""),
        },
    }


def judge_html(html: str, *, tid: int = 0, board_fid: str = "103") -> dict[str, Any]:
    from parsers.content import (
        extract_first_postmessage_html,
        extract_title,
        iter_subresource_title_spans,
    )
    from parsers.links import parse_thread_dual

    title = extract_title(html) or ""
    pm = extract_first_postmessage_html(html) or html
    spans = list(iter_subresource_title_spans(pm) or [])
    parsed = parse_thread_dual(
        html, tid=tid, preferred_link="magnet", board_fid=board_fid
    )
    assets = list(getattr(parsed, "assets", None) or [])
    out = judge_parsed(title=title, assets=assets, title_spans=len(spans))
    out["tid"] = tid
    out["parsed_title"] = title
    return out
