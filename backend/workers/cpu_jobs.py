"""可供 ProcessPool pickle 的顶层解析/判定任务（勿改成闭包）。"""

from __future__ import annotations

from typing import Any


def job_judge_thread_html(payload: dict[str, Any]) -> Any:
    """payload: html + judge_thread_html 的关键字参数。"""
    from workers.thread_outcome import judge_thread_html

    html = payload.get("html") or ""
    kwargs = {k: v for k, v in payload.items() if k != "html"}
    return judge_thread_html(html, **kwargs)


def job_parse_thread_dual(payload: dict[str, Any]) -> Any:
    """payload: html, tid, preferred_link, extra_text, base_url, board_fid。"""
    from parsers.links import parse_thread_dual

    return parse_thread_dual(
        payload.get("html") or "",
        tid=int(payload.get("tid") or 0),
        preferred_link=payload.get("preferred_link") or "both",  # type: ignore[arg-type]
        extra_text=payload.get("extra_text") or "",
        base_url=payload.get("base_url") or "",
        board_fid=payload.get("board_fid") or "",
    )


def job_judge_with_attachment(payload: dict[str, Any]) -> Any:
    """注入附件语料后再判定（整段在子进程，避免主进程 GIL）。"""
    from parsers.attachments import inject_attachment_text
    from workers.thread_outcome import judge_thread_html

    html = payload.get("html") or ""
    attachment_text = payload.get("attachment_text") or ""
    if attachment_text:
        html = inject_attachment_text(html, attachment_text)
    kwargs = {
        k: v
        for k, v in payload.items()
        if k not in {"html", "attachment_text"}
    }
    return judge_thread_html(html, **kwargs)
