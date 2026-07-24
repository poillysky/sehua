"""Format crawler activity log lines with outcome detail."""

from __future__ import annotations

from typing import Any


def format_thread_activity(
    tid: int,
    outcome: dict[str, Any] | None,
    *,
    prefix: str = "抓帖",
    queue_note: str = "",
    soft_browser: bool = False,
) -> str:
    """抓帖活动日志：判定标签 + 具体原因 + 链类型/板块/标题摘要。

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
        parts.append(detail[:100])

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

    return " · ".join(p for p in parts if p)
