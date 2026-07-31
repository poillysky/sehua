"""Format crawler activity log lines with outcome detail."""

from __future__ import annotations

from typing import Any


def _fmt_sec(sec: Any) -> str:
    try:
        s = float(sec)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s < 10:
        return f"{s:.1f}s"
    return f"{s:.0f}s"


def format_thread_activity(
    tid: int,
    outcome: dict[str, Any] | None,
    *,
    prefix: str = "抓帖",
    queue_note: str = "",
    soft_browser: bool = False,
) -> str:
    """抓帖活动日志：判定 + 原因 + 板块/链数/标题 + 总耗时。

    保持 ``tid=123`` 形态，便于管理端渲染可点击链接。
    """
    o = outcome or {}
    verdict = str(o.get("verdict") or "").strip()
    label = str(o.get("verdict_label") or verdict or "").strip()
    detail = str(o.get("outcome") or "").strip()
    title = str(o.get("title") or "").strip()
    kind = str(o.get("primary") or o.get("link_kind") or "").strip()
    board = str(o.get("board_name") or "").strip()
    note = (queue_note or "").strip()

    parts: list[str] = [f"{prefix} tid={int(tid)}"]

    # 前缀已含判定语义时，避免「随机跳过 · 跳过」重复
    skip_label = {
        "随机入库": "正常入库",
        "随机占位": "占位入库",
        "随机跳过": "跳过",
        "随机失败": "失败",
    }.get(prefix)

    # 队列侧更具体时优先（如「重试耗尽出队 · …」「跳过 · 已删占位」）
    if note and note != label and note != skip_label:
        parts.append(note)
    elif label and label != skip_label:
        parts.append(label)

    if detail and detail not in parts and detail != label and detail not in note:
        # 不合格/成功原因常较长，留足展示（活动日志上限 2000）
        parts.append(detail[:180])

    if kind and kind not in {"", "none", "failed"}:
        parts.append(kind)
    elif kind == "failed" and verdict in {"failed", "skipped"}:
        parts.append(kind)

    if board:
        parts.append(board[:48])

    n_m = int(o.get("magnets") or 0)
    n_e = int(o.get("ed2k") or 0)
    n_a = int(o.get("asset_count") or 0)
    if n_a <= 0:
        n_a = n_m + n_e
    if n_m or n_e:
        bits: list[str] = []
        if n_m:
            bits.append(f"磁力×{n_m}")
        if n_e:
            bits.append(f"ed2k×{n_e}")
        if n_a > max(n_m, n_e):
            bits.append(f"共{n_a}链")
        parts.append(" ".join(bits))

    if title:
        parts.append(title[:40])

    if soft_browser:
        parts.append("软文浏览器重读")

    # 总耗时 + 读/附拆分（有则带）
    total = _fmt_sec(o.get("elapsed_sec"))
    read = _fmt_sec(o.get("read_sec"))
    attach = _fmt_sec(o.get("attach_sec"))
    apath = str(o.get("attach_path") or "").strip()
    timing_bits: list[str] = []
    if total:
        timing_bits.append(f"总{total}")
    if read:
        timing_bits.append(f"读{read}")
    if attach:
        timing_bits.append(f"附{attach}" + (f"/{apath}" if apath else ""))
    if timing_bits:
        parts.append(" ".join(timing_bits))

    return " · ".join(p for p in parts if p)
