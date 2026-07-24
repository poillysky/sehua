"""随机抓帖：按 tid 直链探测早期帖，both 链判定入库。

不写 crawl_pages 待抓队列；本会话已探测 tid 仅记在内存，
停止/结束后清空，下次启动重新随机抽样。
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Any, Optional

from crawler.list_urls import site_root
from crawler.session import BASE_URL
from crawler.throttle import THROTTLE
from db.connection import connect
from db.forum_configs import SITE_CRAWLER_FORUM_ID, load_forum_configs_map
from db.queue import canonical_thread_url, is_thread_known
from parsers.boards import get_board_policy
from parsers.thread_gates import extract_board_fid, page_title
from workers.pipeline import process_thread
from workers.runner import (
    _STATE,
    _log_activity,
    end_exclusive,
    recover_stuck_after_stop,
    try_begin_exclusive,
)
from workers.session_factory import fetcher_from_config, session_from_config

log = logging.getLogger(__name__)

DEFAULT_TID_MIN = 80_000
DEFAULT_TID_MAX = 500_000
DEFAULT_PROBE = 200
# 0 = 不按入库数提前结束，跑满本轮探测数
DEFAULT_IMPORT_TARGET = 0

# 本会话内已抽中的 tid（不进库队列）；停止/结束时清空
_session_probed: set[int] = set()


def _empty_random_progress(*, active: bool = False, probe_budget: int = DEFAULT_PROBE) -> dict[str, Any]:
    return {
        "active": active,
        "probe_budget": int(probe_budget),
        "probed": 0,
        "imported": 0,
        "stubbed": 0,
        "missing": 0,
        "skipped_dup": 0,
        "failed": 0,
        "skipped": 0,
        "session_probed": len(_session_probed),
    }


def _publish_random_progress(
    result: dict[str, Any] | None = None,
    *,
    probe_budget: int | None = None,
    active: bool = True,
) -> None:
    """把本轮计数写到 _STATE，供状态接口轮询。"""
    base = _empty_random_progress(
        active=active,
        probe_budget=probe_budget if probe_budget is not None else DEFAULT_PROBE,
    )
    if result:
        for key in (
            "probed",
            "imported",
            "stubbed",
            "missing",
            "skipped_dup",
            "failed",
            "skipped",
        ):
            if key in result:
                base[key] = int(result.get(key) or 0)
        if result.get("probe_budget") is not None:
            base["probe_budget"] = int(result["probe_budget"])
    base["session_probed"] = len(_session_probed)
    base["active"] = active
    _STATE["random_progress"] = base


def random_progress() -> dict[str, Any]:
    cur = _STATE.get("random_progress")
    if isinstance(cur, dict) and cur:
        out = dict(cur)
        out["session_probed"] = len(_session_probed)
        return out
    return _empty_random_progress(active=False)


def clear_random_session_state() -> None:
    """循环结束或暂停：清空本会话抽样记录，下次重新生成。"""
    _session_probed.clear()
    _publish_random_progress(active=False)


MISSING_MARKERS = (
    "主题不存在",
    "抱歉，指定的主题不存在",
    "指定的主题不存在",
    "没有找到主题",
    "没有找到帖子",
    "帖子不存在",
    "内容不存在或已被删除",
)


def sample_tids(
    lo: int,
    hi: int,
    n: int,
    *,
    exclude: set[int] | None = None,
    rng: random.Random | None = None,
) -> list[int]:
    """从 [lo, hi] 不重复抽 n 个 tid（可用池不足则抽满池）。"""
    low = min(int(lo), int(hi))
    high = max(int(lo), int(hi))
    if high < low:
        return []
    ban = set(exclude or ())
    pool_size = high - low + 1
    need = max(0, int(n))
    if need <= 0 or pool_size <= 0:
        return []
    r = rng or random.Random()
    if pool_size - len(ban) <= need:
        return [t for t in range(low, high + 1) if t not in ban]
    out: list[int] = []
    seen: set[int] = set(ban)
    guard = 0
    while len(out) < need and guard < need * 40 + 100:
        guard += 1
        tid = r.randint(low, high)
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def is_missing_thread(html: str, title: str = "") -> bool:
    """识别 Discuz「主题不存在」等空洞页（委托 thread_gates）。"""
    from parsers.thread_gates import is_missing_thread as _gate_missing

    return _gate_missing(html, title)


def is_tid_known(conn: Any, tid: int, thread_url: str) -> bool:
    """已入库资源或已在 crawl_pages（其它入口写入）则跳过；随机模式自身不写队列。"""
    url = canonical_thread_url(thread_url) or thread_url
    if is_thread_known(conn, url):
        return True
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM crawl_pages
        WHERE page_type = 'thread' AND tid = %s
        LIMIT 1
        """,
        (int(tid),),
    )
    if cur.fetchone():
        return True
    cur.execute(
        """
        SELECT 1 FROM resource_sources
        WHERE source_url = %s
           OR source_url LIKE %s
        LIMIT 1
        """,
        (url, f"%thread-{int(tid)}-%"),
    )
    return bool(cur.fetchone())


async def run_random_tid_batch(
    *,
    forum_id: str = SITE_CRAWLER_FORUM_ID,
    probe: int | None = None,
    import_target: int | None = None,
    tid_min: int | None = None,
    tid_max: int | None = None,
    persist: bool = True,
    crawler_config: Optional[dict[str, Any]] = None,
    from_loop: bool = False,
) -> dict[str, Any]:
    """随机探测早期 tid：magnet+ed2k 混合判定。

    import_target <= 0：不按入库数早停，跑满本轮 probe。
    from_loop=True：由连续循环占用 running，本函数不再抢/释 exclusive。
    """
    if not from_loop:
        gate = try_begin_exclusive("random_tid")
        if not gate.get("ok"):
            return {
                "ok": False,
                "skipped": True,
                "reason": gate.get("reason"),
                "error": gate.get("error"),
            }
        THROTTLE.clear_stop()

    cfg = dict(crawler_config or {})
    if not cfg:
        conn = connect()
        try:
            configs = load_forum_configs_map(conn)
            cfg = dict(configs.get(forum_id) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        finally:
            conn.close()

    lo = int(tid_min if tid_min is not None else cfg.get("web_crawler_random_tid_min") or DEFAULT_TID_MIN)
    hi = int(tid_max if tid_max is not None else cfg.get("web_crawler_random_tid_max") or DEFAULT_TID_MAX)
    max_probe = max(1, int(probe if probe is not None else cfg.get("web_crawler_random_tid_probe") or DEFAULT_PROBE))
    if import_target is not None:
        target = int(import_target)
    else:
        raw_t = cfg.get("web_crawler_random_tid_import_target")
        target = int(raw_t) if raw_t is not None else DEFAULT_IMPORT_TARGET
    # target<=0：跑满 probe；>0：入库+占位达目标可提前结束
    stop_on_persisted = target > 0
    if hi < lo:
        lo, hi = hi, lo

    result: dict[str, Any] = {
        "ok": True,
        "tid_min": lo,
        "tid_max": hi,
        "probe_budget": max_probe,
        "import_target": target,
        "probed": 0,
        "missing": 0,
        "skipped_dup": 0,
        "imported": 0,
        "stubbed": 0,
        "failed": 0,
        "skipped": 0,
        "other": 0,
        "samples": [],
    }

    root = site_root(str(cfg.get("web_crawl_urls") or "").split(",")[0] if cfg else BASE_URL)
    session = session_from_config(cfg)
    fetcher = fetcher_from_config(session, cfg)
    # 本会话已抽过的 + 本批已抽的，避免同会话重复抽号（仍不写队列）
    used: set[int] = set(_session_probed)

    target_label = f"入库目标 {target}" if stop_on_persisted else "跑满本轮探测"
    _log_activity(
        f"随机抓帖开始 · tid[{lo},{hi}] · 探测 {max_probe} · {target_label} · 不进队列 · both 链"
    )
    _STATE["phase"] = "random_tid"
    _publish_random_progress(result, probe_budget=max_probe, active=True)

    try:
        if not session._ready:
            await session.bootstrap()

        candidates = sample_tids(lo, hi, max_probe, exclude=used)
        for tid in candidates:
            if THROTTLE.should_stop() or (from_loop and not _STATE.get("looping")):
                result["reason"] = "stopped"
                break
            if stop_on_persisted and result["imported"] + result["stubbed"] >= target:
                break
            if result["probed"] >= max_probe:
                break

            used.add(tid)
            _session_probed.add(tid)
            thread_url = f"{root}thread-{tid}-1-1.html"
            result["probed"] += 1

            try:
                # 去重：已入库 / 其它入口已写入 crawl_pages → 跳过（本模式不写队列）
                try:
                    conn = connect()
                    try:
                        known = is_tid_known(conn, tid, thread_url)
                    finally:
                        conn.close()
                except Exception:
                    known = False
                if known:
                    result["skipped_dup"] += 1
                    result["samples"].append({"tid": tid, "status": "dup"})
                    continue

                await THROTTLE.sleep()
                if THROTTLE.should_stop() or (from_loop and not _STATE.get("looping")):
                    result["reason"] = "stopped"
                    break

                try:
                    html = await fetcher.get_thread_html(
                        thread_url, retries=int(cfg.get("web_crawler_fetch_retries") or 3)
                    )
                except Exception as exc:
                    result["failed"] += 1
                    result["other"] += 1
                    result["samples"].append({"tid": tid, "status": "fetch_error", "error": str(exc)[:120]})
                    _log_activity(f"随机 tid={tid} · 取页失败 · {exc}")
                    continue

                title = page_title(html)
                if is_missing_thread(html, title):
                    result["missing"] += 1
                    result["samples"].append({"tid": tid, "status": "missing", "title": title[:80]})
                    _log_activity(f"随机 tid={tid} · 主题不存在")
                    continue

                fid = extract_board_fid(html) or 0
                pol = get_board_policy(int(fid) if fid else 0)
                board_fid = int(pol.fid) if fid else 0
                board_name = pol.name if fid else "未知板块"

                try:
                    outcome = await process_thread(
                        tid,
                        board_fid=board_fid if board_fid else 0,
                        board_name=board_name,
                        session=session,
                        list_title=title,
                        persist=persist,
                        crawler_config=cfg,
                        fetcher=fetcher,
                        preferred_link="both",
                        html=html,
                    )
                except Exception as exc:
                    result["failed"] += 1
                    result["other"] += 1
                    result["samples"].append({"tid": tid, "status": "error", "error": str(exc)[:120]})
                    _log_activity(f"随机 tid={tid} · 判定异常 · {exc}")
                    continue

                verdict = str(outcome.get("verdict") or "failed")
                sample = {
                    "tid": tid,
                    "fid": board_fid or None,
                    "title": (outcome.get("title") or title or "")[:80],
                    "verdict": verdict,
                    "status": verdict,
                }
                result["samples"].append(sample)

                if verdict == "import":
                    result["imported"] += 1
                    THROTTLE.record_success()
                    from workers.activity_format import format_thread_activity

                    _log_activity(
                        format_thread_activity(
                            tid,
                            {**outcome, "board_name": board_name or outcome.get("board_name")},
                            prefix="随机入库",
                        )
                    )
                elif verdict == "stub":
                    result["stubbed"] += 1
                    THROTTLE.record_success()
                    from workers.activity_format import format_thread_activity

                    _log_activity(
                        format_thread_activity(tid, outcome, prefix="随机占位")
                    )
                elif verdict == "skipped":
                    result["skipped"] += 1
                    THROTTLE.record_success()
                    from workers.activity_format import format_thread_activity

                    _log_activity(
                        format_thread_activity(tid, outcome, prefix="随机跳过")
                    )
                elif verdict == "failed":
                    result["failed"] += 1
                    from workers.activity_format import format_thread_activity

                    _log_activity(
                        format_thread_activity(tid, outcome, prefix="随机失败")
                    )
                else:
                    result["other"] += 1
                    from workers.activity_format import format_thread_activity

                    _log_activity(
                        format_thread_activity(
                            tid,
                            outcome,
                            prefix=f"随机{verdict}",
                        )
                    )

                if stop_on_persisted and result["imported"] + result["stubbed"] >= target:
                    break
            finally:
                _publish_random_progress(result, probe_budget=max_probe, active=True)

        persisted_n = result["imported"] + result["stubbed"]
        _log_activity(
            f"随机抓帖本轮结束 · 探测 {result['probed']} · 缺失 {result['missing']} · "
            f"重复 {result['skipped_dup']} · 入库 {result['imported']}+占位 {result['stubbed']}"
            + (f" · 目标 {target}" if stop_on_persisted else "")
        )
        result["persisted_total"] = persisted_n
        _STATE["last_result"] = {
            "ok": True,
            "mode": "random_tid",
            **{k: result[k] for k in (
                "probed", "missing", "skipped_dup", "imported", "stubbed", "failed", "skipped",
            )},
        }
        _STATE["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # 单轮结束仍标 active（循环会马上开下一轮）；仅最终 stop 才清 active
        _publish_random_progress(
            result,
            probe_budget=max_probe,
            active=bool(from_loop and _STATE.get("looping") and not THROTTLE.should_stop()),
        )
        return result
    except Exception as exc:
        log.exception("random_tid batch failed")
        _log_activity(f"随机抓帖异常 · {exc}")
        result["ok"] = False
        result["error"] = str(exc)
        _STATE["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _publish_random_progress(result, probe_budget=max_probe, active=False)
        return result
    finally:
        try:
            await session.close()
        except Exception:
            pass
        if not from_loop:
            clear_random_session_state()
            end_exclusive()


_random_loop_task: asyncio.Task | None = None
_random_loop_future: Any = None


async def _random_tid_loop(
    *,
    forum_id: str = SITE_CRAWLER_FORUM_ID,
    probe: int = DEFAULT_PROBE,
    tid_min: int | None = None,
    tid_max: int | None = None,
) -> None:
    """每轮随机探测 probe 个 tid，一轮结束立即再开。"""
    clear_random_session_state()
    _STATE["looping"] = True
    _STATE["running"] = True
    _STATE["loop_kind"] = "random_tid"
    _STATE["phase"] = "random_tid"
    _log_activity(f"随机抓帖连续调度已启动 · 每轮 {probe} 帖 · 不进队列 · 跳过已入库")
    try:
        while _STATE.get("looping") and not THROTTLE.should_stop():
            await run_random_tid_batch(
                forum_id=forum_id,
                probe=probe,
                import_target=0,
                tid_min=tid_min,
                tid_max=tid_max,
                persist=True,
                from_loop=True,
            )
            if THROTTLE.should_stop() or not _STATE.get("looping"):
                break
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        _log_activity("随机抓帖连续任务已取消")
        raise
    finally:
        clear_random_session_state()
        _STATE["looping"] = False
        _STATE["running"] = False
        _STATE["loop_kind"] = None
        _STATE["phase"] = "idle"
        _log_activity("随机抓帖连续调度已停止 · 本会话抽样已清空")


def start_random_tid_loop(
    *,
    forum_id: str = SITE_CRAWLER_FORUM_ID,
    probe: int | None = None,
    tid_min: int | None = None,
    tid_max: int | None = None,
) -> dict[str, Any]:
    """启动随机抓帖连续循环（与深扫连续调度互斥）。"""
    global _random_loop_task, _random_loop_future
    from workers.crawl_executor import spawn_crawl

    if _STATE.get("looping"):
        kind = _STATE.get("loop_kind") or "deep"
        if kind == "random_tid" and (
            (_random_loop_future is not None and not _random_loop_future.done())
            or (_random_loop_task is not None and not _random_loop_task.done())
        ):
            return {"ok": True, "already": True, "message": "随机抓帖连续调度已在运行"}
        return {
            "ok": False,
            "reason": "loop_running",
            "error": "已有连续调度在运行，请先停止",
        }
    recover_stuck_after_stop()
    if _STATE.get("running"):
        return {"ok": False, "reason": "busy", "error": "爬虫正在执行，请稍候"}

    n = max(1, int(probe if probe is not None else DEFAULT_PROBE))
    clear_random_session_state()
    THROTTLE.clear_stop()
    _STATE["looping"] = True
    _STATE["running"] = True
    _STATE["loop_kind"] = "random_tid"
    _STATE["phase"] = "random_tid"
    _STATE["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    async def _boot() -> None:
        global _random_loop_task
        _random_loop_task = asyncio.current_task()
        try:
            await _random_tid_loop(
                forum_id=forum_id, probe=n, tid_min=tid_min, tid_max=tid_max
            )
        finally:
            if _random_loop_task is asyncio.current_task():
                _random_loop_task = None

    _random_loop_future = spawn_crawl(_boot(), name="random-tid-loop")
    return {"ok": True, "message": f"随机抓帖连续调度已启动 · 每轮 {n} · 不进队列", "probe": n}


def stop_random_tid_loop() -> dict[str, Any]:
    from workers.runner import request_stop

    request_stop()
    return {"ok": True, "message": "已请求停止随机抓帖连续调度"}


def cancel_random_loop_task() -> list[asyncio.Task]:
    """供 stop_crawler 强制取消。"""
    tasks: list[asyncio.Task] = []
    t = _random_loop_task
    if t is not None and not t.done():
        tasks.append(t)
    return tasks
