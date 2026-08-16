"""随机抓帖：按 tid 直链探测早期帖，both 链判定入库。

已探 tid 持久化到 random_tid_probes（重启仍跳过）。
抽样可按白名单板块已有帖号分布自适应窗口，提高命中率。
本会话内存 _session_probed 仅作加速；停止时不清数据库记录。
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
from crawler.sites import get_site_adapter
from crawler.throttle import THROTTLE
from db.connection import connect
from db.forum_configs import (
    SITE_CRAWLER_FORUM_ID,
    load_forum_configs_map,
    resolve_enabled_board_fids,
)
from db.queue import canonical_thread_url, is_thread_known
from db.random_probes import (
    collect_whitelist_tids,
    count_probed,
    ensure_random_probes_schema,
    estimate_tid_range,
    load_known_tids_for_exclude,
    load_probed_tids,
    record_probe,
)
from db.resource_db import connect_resource
from parsers.thread_gates import extract_board_fid, page_title
from workers.pipeline import process_thread
from workers.runner import (
    _STATE,
    _log_activity,
    end_exclusive,
    recover_stuck_after_stop,
    try_begin_exclusive,
)
from workers.session_factory import (
    bootstrap_probe_for_forum,
    resolve_forum_entry_urls,
    fetcher_from_config,
    session_from_config,
)

log = logging.getLogger(__name__)

DEFAULT_TID_MIN = 80_000
DEFAULT_TID_MAX = 500_000
DEFAULT_PROBE = 500
# 0 = 不按入库数提前结束，跑满本轮探测数
DEFAULT_IMPORT_TARGET = 0

# 本会话内已抽中的 tid（加速）；持久化以 DB 为准
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
        "samples": [],
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
        if result.get("persist_probed") is not None:
            base["persist_probed"] = int(result["persist_probed"])
        if result.get("adaptive") is not None:
            base["adaptive"] = bool(result["adaptive"])
        samples = result.get("samples")
        if isinstance(samples, list):
            # 弹窗「目前」展示本轮最近探测（倒序）
            base["samples"] = list(reversed(samples[-120:]))
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
    """循环结束或暂停：仅清空内存抽样缓存；数据库已探记录保留。"""
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


def sample_tids_weighted(
    windows: list[tuple[int, int, float]],
    n: int,
    *,
    exclude: set[int] | None = None,
    rng: random.Random | None = None,
) -> list[int]:
    """按窗口权重抽样；窗口内均匀，全局去重。"""
    r = rng or random.Random()
    ban = set(exclude or ())
    need = max(0, int(n))
    if need <= 0 or not windows:
        return []
    weights = [max(0.0, float(w)) for _, _, w in windows]
    total_w = sum(weights) or 1.0
    quotas: list[int] = []
    assigned = 0
    for i, w in enumerate(weights):
        if i == len(weights) - 1:
            quotas.append(max(0, need - assigned))
        else:
            q = int(need * (w / total_w))
            quotas.append(q)
            assigned += q
    out: list[int] = []
    seen = set(ban)
    for (lo, hi, _w), q in zip(windows, quotas):
        if q <= 0:
            continue
        chunk = sample_tids(lo, hi, q, exclude=seen, rng=r)
        for t in chunk:
            if t not in seen:
                seen.add(t)
                out.append(t)
    if len(out) < need and windows:
        glo = min(a for a, _b, _w in windows)
        ghi = max(b for _a, b, _w in windows)
        extra = sample_tids(glo, ghi, need - len(out), exclude=seen, rng=r)
        out.extend(extra)
    return out[:need]


def is_missing_thread(html: str, title: str = "") -> bool:
    """识别 Discuz「主题不存在」等空洞页（委托 thread_gates）。"""
    from parsers.thread_gates import is_missing_thread as _gate_missing

    return _gate_missing(html, title)


def is_tid_known(
    conn: Any,
    tid: int,
    thread_url: str,
    *,
    forum_id: str = "",
) -> bool:
    """已入库资源或已在 crawl_pages（其它入口写入）则跳过；随机模式自身不写队列。

    resource_sources 只用规范 URL 等值查询（勿 OR LIKE '%thread-tid%'，会 seq scan）。
    """
    from db.resource_db import connect_resource

    url = canonical_thread_url(thread_url, forum_id=forum_id) or thread_url
    if is_thread_known(conn, url):
        return True
    fid = (forum_id or "").strip()
    cur = conn.cursor()
    if fid:
        cur.execute(
            """
            SELECT 1 FROM crawl_pages
            WHERE page_type = 'thread' AND tid = %s AND forum_id = %s
            LIMIT 1
            """,
            (int(tid), fid),
        )
    else:
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
    rconn = connect_resource()
    try:
        with rconn.cursor() as rcur:
            if fid:
                rcur.execute(
                    """
                    SELECT 1 FROM resource_sources
                    WHERE source_url = %s
                      AND (forum_id = %s OR forum_id IS NULL OR forum_id = '')
                    LIMIT 1
                    """,
                    (url, fid),
                )
            else:
                rcur.execute(
                    """
                    SELECT 1 FROM resource_sources
                    WHERE source_url = %s
                    LIMIT 1
                    """,
                    (url,),
                )
            return bool(rcur.fetchone())
    finally:
        if rconn is not conn:
            try:
                rconn.close()
            except Exception:
                pass


def _persist_probe(
    *,
    forum_id: str,
    tid: int,
    outcome: str,
    board_fid: str | int | None = None,
    title: str | None = None,
) -> bool:
    """写入已探记录。成功 True；失败 False（调用方应中止本轮，避免无落库再探）。"""
    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            conn = connect()
            try:
                ensure_random_probes_schema(conn)
                record_probe(
                    conn,
                    forum_id=forum_id,
                    tid=tid,
                    outcome=outcome,
                    board_fid=board_fid,
                    title=title,
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as exc:
            last_exc = exc
            log.exception("persist random probe tid=%s attempt", tid)
    if last_exc is not None:
        log.error("persist random probe tid=%s failed: %s", tid, last_exc)
    return False


def _load_exclude_tids(*, forum_id: str) -> tuple[set[int], int, int]:
    """加载抽样排除集：(probes∪known, probes_count, known_extra_count)。

    任一关键表读取失败则抛错，由调用方中止本轮。
    """
    meta = connect()
    try:
        ensure_random_probes_schema(meta)
        try:
            meta.commit()
        except Exception:
            pass
        probed = load_probed_tids(meta, forum_id)
        persist_n = count_probed(meta, forum_id)
        rconn = None
        try:
            rconn = connect_resource()
        except Exception:
            rconn = None
        try:
            known = load_known_tids_for_exclude(meta, rconn, forum_id=forum_id)
        finally:
            if rconn is not None:
                try:
                    rconn.close()
                except Exception:
                    pass
    finally:
        meta.close()
    merged = set(probed) | set(known)
    known_extra = len(merged) - len(probed)
    return merged, int(persist_n), max(0, known_extra)


def _resolve_sampling_plan(
    *,
    forum_id: str,
    cfg: dict[str, Any],
    cfg_lo: int,
    cfg_hi: int,
    enabled: list[str],
) -> dict[str, Any]:
    adaptive_on = str(cfg.get("web_crawler_random_adaptive", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    plan = estimate_tid_range([], cfg_lo=cfg_lo, cfg_hi=cfg_hi)
    if not adaptive_on:
        return plan
    try:
        meta = connect()
        try:
            ensure_random_probes_schema(meta)
            rconn = None
            try:
                rconn = connect_resource()
            except Exception:
                rconn = None
            try:
                wl = collect_whitelist_tids(
                    meta,
                    rconn,
                    forum_id=forum_id,
                    enabled_keys=enabled,
                )
            finally:
                if rconn is not None:
                    try:
                        rconn.close()
                    except Exception:
                        pass
            plan = estimate_tid_range(wl, cfg_lo=cfg_lo, cfg_hi=cfg_hi)
        finally:
            meta.close()
    except Exception:
        log.exception("estimate tid range failed")
    return plan


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

    # 与连续深扫一致：论坛 cfg + 通用设置里的代理（随机路径以前漏读 proxy）
    from db.settings_store import get_setting

    cfg = dict(crawler_config or {})
    proxy = ""
    conn = connect()
    try:
        if not cfg:
            configs = load_forum_configs_map(conn)
            cfg = dict(configs.get(forum_id) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        proxy = (get_setting(conn, "web_crawler_proxy", "") or "").strip()
        cookie = (get_setting(conn, "web_crawler_cookie", "") or "").strip()
        if cookie:
            cfg["web_crawler_cookie"] = cookie
    finally:
        conn.close()
    if proxy:
        cfg["web_crawler_proxy"] = proxy

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
        "proxy_configured": bool(proxy),
    }

    root = site_root(str(cfg.get("web_crawl_urls") or "").split(",")[0] if cfg else BASE_URL)
    adapter = get_site_adapter(forum_id)
    session = session_from_config(cfg, proxy=proxy, forum_id=forum_id)
    fetcher = fetcher_from_config(session, cfg, proxy=proxy)

    enabled = resolve_enabled_board_fids(cfg, forum_id=forum_id)
    persist_n = 0
    known_extra = 0
    used: set[int] = set(_session_probed)
    try:
        db_exclude, persist_n, known_extra = _load_exclude_tids(forum_id=forum_id)
        used |= db_exclude
    except Exception as exc:
        log.exception("load exclude tids")
        result["ok"] = False
        result["reason"] = "load_exclude_failed"
        result["error"] = str(exc)[:200]
        _log_activity(f"随机抓帖中止 · 无法加载已探/已入库 tid · {exc}")
        _publish_random_progress(result, probe_budget=max_probe, active=False)
        if not from_loop:
            clear_random_session_state()
            end_exclusive()
        try:
            await session.close()
        except Exception:
            pass
        return result

    plan = _resolve_sampling_plan(
        forum_id=forum_id,
        cfg=cfg,
        cfg_lo=lo,
        cfg_hi=hi,
        enabled=enabled,
    )
    windows = list(plan.get("windows") or [(lo, hi, 1.0)])
    result["adaptive"] = bool(plan.get("adaptive"))
    result["persist_probed"] = int(persist_n)
    result["exclude_known"] = int(known_extra)
    result["tid_min"] = int(plan.get("lo") or lo)
    result["tid_max"] = int(plan.get("hi") or hi)

    target_label = f"入库目标 {target}" if stop_on_persisted else "跑满本轮探测"
    adapt_label = (
        f"自适应 tid[{plan.get('lo')},{plan.get('hi')}] · 样本 {plan.get('sample_n')}"
        if plan.get("adaptive")
        else f"固定 tid[{lo},{hi}]"
    )
    _log_activity(
        f"随机抓帖开始 · {forum_id} · {adapt_label} · 已探库 {persist_n}"
        + (f" · 另排除已入库 {known_extra}" if known_extra else "")
        + f" · 探测 {max_probe} · {target_label} · 不进队列 · both 链"
        + (f" · 代理 {proxy}" if proxy else " · 无代理")
    )
    _STATE["phase"] = "random_tid"
    _publish_random_progress(result, probe_budget=max_probe, active=True)

    try:
        if not session._ready:
            entries = resolve_forum_entry_urls(cfg, forum_id, proxy=proxy)
            probe = bootstrap_probe_for_forum(cfg, forum_id, proxy=proxy)
            await session.bootstrap(entry_urls=entries or None, probe_url=probe)
            root = site_root(session.active_entry_url or (entries[0] if entries else root))
            _log_activity(
                f"随机进站就绪"
                + (f" · 代理 {proxy}" if proxy else " · 无代理")
            )

        candidates = sample_tids_weighted(windows, max_probe, exclude=used)

        def _ok_persist(**kwargs: Any) -> bool:
            if _persist_probe(**kwargs):
                return True
            result["ok"] = False
            result["reason"] = "persist_probe_failed"
            result["error"] = f"persist tid={kwargs.get('tid')} failed"
            _log_activity(f"随机抓帖中止 · 已探落库失败 tid={kwargs.get('tid')}")
            return False

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
            thread_url = adapter.build_thread_url(root, tid)
            result["probed"] += 1

            try:
                # 去重：已入库 / 其它入口已写入 crawl_pages → 跳过（本模式不写队列）
                try:
                    conn = connect()
                    try:
                        known = is_tid_known(conn, tid, thread_url, forum_id=forum_id)
                    finally:
                        conn.close()
                except Exception:
                    known = False
                if known:
                    result["skipped_dup"] += 1
                    result["samples"].append({"tid": tid, "status": "dup"})
                    if not _ok_persist(forum_id=forum_id, tid=tid, outcome="dup"):
                        break
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
                    if not _ok_persist(forum_id=forum_id, tid=tid, outcome="fetch_error"):
                        break
                    _log_activity(f"随机 tid={tid} · 取页失败 · {exc}")
                    continue

                title = page_title(html)
                if is_missing_thread(html, title):
                    result["missing"] += 1
                    result["samples"].append({"tid": tid, "status": "missing", "title": title[:80]})
                    if not _ok_persist(
                        forum_id=forum_id, tid=tid, outcome="missing", title=title[:80]
                    ):
                        break
                    _log_activity(f"随机 tid={tid} · 主题不存在")
                    continue

                fid = extract_board_fid(html) or 0
                pol = adapter.get_board_policy(int(fid) if fid else 0)
                board_fid = int(pol.fid) if fid else 0
                board_name = pol.name if fid else "未知板块"
                board_key = pol.key if fid else (str(board_fid) if board_fid else None)

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
                        forum_id=forum_id,
                    )
                except Exception as exc:
                    result["failed"] += 1
                    result["other"] += 1
                    result["samples"].append({"tid": tid, "status": "error", "error": str(exc)[:120]})
                    if not _ok_persist(
                        forum_id=forum_id,
                        tid=tid,
                        outcome="error",
                        board_fid=board_key,
                        title=title[:80],
                    ):
                        break
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
                if not _ok_persist(
                    forum_id=forum_id,
                    tid=tid,
                    outcome=verdict,
                    board_fid=board_key or outcome.get("board_fid"),
                    title=sample["title"],
                ):
                    break

                if verdict == "import":
                    result["imported"] += 1
                    THROTTLE.record_success()
                    from workers.import_rate import note_persisted

                    note_persisted(kind="import")
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
                    from workers.import_rate import note_persisted

                    note_persisted(kind="stub")
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
            + (f" · 自适应" if result.get("adaptive") else "")
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
    scan_head_first: bool = True,
) -> dict[str, Any]:
    """启动随机抓帖连续循环（与深扫连续调度互斥）。

    默认 scan_head_first=True：先扫新帖（全板入队并消化至空），再持续随机抓帖。
    """
    global _random_loop_task, _random_loop_future
    from workers.crawl_executor import spawn_crawl

    if _STATE.get("looping"):
        kind = _STATE.get("loop_kind") or "deep"
        if kind == "random_tid" and (
            (_random_loop_future is not None and not _random_loop_future.done())
            or (_random_loop_task is not None and not _random_loop_task.done())
        ):
            return {"ok": True, "already": True, "message": "随机连续调度已在运行"}
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
    _STATE["phase"] = "scan_head" if scan_head_first else "random_tid"
    _STATE["forum_id"] = forum_id
    _STATE["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    async def _boot() -> None:
        global _random_loop_task
        _random_loop_task = asyncio.current_task()
        entered_random = False
        try:
            if scan_head_first:
                from workers.runner import run_scan_head_once

                _log_activity(
                    f"随机 · 1/2 扫新帖（全板入队→消化队列至空）· 随后每轮 {n} 随机抓帖"
                )
                scan = await run_scan_head_once(
                    forum_id=forum_id,
                    persist=True,
                    hold_lock=True,
                )
                if THROTTLE.should_stop() or scan.get("reason") == "stopped":
                    _log_activity("随机 · 扫新帖阶段已停止 · 不进入随机抓帖")
                    return
                if scan.get("ok") is False and not scan.get("skipped"):
                    _log_activity(
                        f"随机 · 扫新帖失败 · {scan.get('error') or scan.get('reason') or '未知'} · 不进入随机"
                    )
                    return
                if THROTTLE.should_stop() or not _STATE.get("looping"):
                    return
                _log_activity(
                    f"随机 · 2/2 扫新帖完成 · 入队 {scan.get('enqueued') or 0} · "
                    f"抓 {scan.get('crawled') or 0} · 开始持续随机抓帖"
                )
            entered_random = True
            await _random_tid_loop(
                forum_id=forum_id, probe=n, tid_min=tid_min, tid_max=tid_max
            )
        except asyncio.CancelledError:
            _log_activity("随机管道已取消")
            raise
        finally:
            if _random_loop_task is asyncio.current_task():
                _random_loop_task = None
            if not entered_random:
                clear_random_session_state()
                _STATE["looping"] = False
                _STATE["running"] = False
                _STATE["loop_kind"] = None
                _STATE["forum_id"] = None
                _STATE["phase"] = "idle"
                _STATE["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    _random_loop_future = spawn_crawl(_boot(), name="random-tid-loop")
    msg = (
        f"随机已启动 · 先扫新帖再每轮 {n} 随机抓帖 · 不进队列"
        if scan_head_first
        else f"随机抓帖连续调度已启动 · 每轮 {n} · 不进队列"
    )
    return {"ok": True, "message": msg, "probe": n, "scan_head_first": bool(scan_head_first)}


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
