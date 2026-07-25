"""资源库单份滚动备份：pg_dump → gzip 覆盖；备份前停爬虫、结束后恢复。"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from db.connection import connect
from db.forum_configs import (
    FULL_CRAWLER_FORUM_IDS,
    enabled_crawler_forum_ids,
    get_active_forum_id,
    load_forum_configs_map,
    save_forum_config,
)
from db.resource_db import connect_resource, resource_dsn_kwargs
from db.settings_store import get_setting, set_setting

log = logging.getLogger(__name__)

BACKUP_FILENAME = "ed2k-resources.sql.gz"
_DEFAULT_BACKUP_DIR = Path(__file__).resolve().parent.parent / "data" / "backups"


def _resolve_backup_dir() -> Path:
    raw = (os.getenv("BACKUP_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_BACKUP_DIR


# 可被测试 monkeypatch；默认读环境变量 BACKUP_DIR（compose 映射到宿主机 data/backups）
BACKUP_DIR = _resolve_backup_dir()
BACKUP_PATH = BACKUP_DIR / BACKUP_FILENAME
BACKUP_TMP_PATH = BACKUP_DIR / f"{BACKUP_FILENAME}.tmp"

# 资源本体相关表（不含爬虫队列 / 活动日志）
BACKUP_TABLES: tuple[str, ...] = (
    "ed2k_resources",
    "resource_sources",
    "resource_tags",
    "tags",
    "import_jobs",
)

_LOCK = threading.Lock()
_BUSY = False
_SCHEDULER_TASK: Optional[asyncio.Task[None]] = None

SETTING_ENABLED = "backup_enabled"
SETTING_HOUR = "backup_hour"
SETTING_MINUTE = "backup_minute"
SETTING_LAST_OK = "backup_last_ok"
SETTING_LAST_AT = "backup_last_at"
SETTING_LAST_ERROR = "backup_last_error"
SETTING_LAST_BYTES = "backup_last_bytes"
SETTING_LAST_RUN_DATE = "backup_last_run_date"


def is_backup_busy() -> bool:
    return _BUSY


def backup_file_info() -> dict[str, Any]:
    p = BACKUP_PATH
    if not p.is_file():
        return {"exists": False, "path": str(p), "filename": BACKUP_FILENAME, "bytes": 0, "mtime": None}
    st = p.stat()
    return {
        "exists": True,
        "path": str(p),
        "filename": BACKUP_FILENAME,
        "bytes": int(st.st_size),
        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
    }


def load_backup_config(conn: Any | None = None) -> dict[str, Any]:
    own = conn is None
    if own:
        conn = connect()
    try:
        enabled = get_setting(conn, SETTING_ENABLED, "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        hour = int(get_setting(conn, SETTING_HOUR, "3") or 3)
        minute = int(get_setting(conn, SETTING_MINUTE, "0") or 0)
        hour = max(0, min(23, hour))
        minute = max(0, min(59, minute))
        return {
            "enabled": enabled,
            "hour": hour,
            "minute": minute,
            "last_ok": get_setting(conn, SETTING_LAST_OK, "") == "1",
            "last_at": get_setting(conn, SETTING_LAST_AT, "") or None,
            "last_error": get_setting(conn, SETTING_LAST_ERROR, "") or None,
            "last_bytes": int(get_setting(conn, SETTING_LAST_BYTES, "0") or 0),
            "last_run_date": get_setting(conn, SETTING_LAST_RUN_DATE, "") or None,
            "file": backup_file_info(),
            "busy": is_backup_busy(),
            "import_job": _import_job_snapshot(),
        }
    finally:
        if own:
            conn.close()


def _import_job_snapshot() -> dict[str, Any]:
    try:
        from workers.backup_import import get_import_progress

        return get_import_progress()
    except Exception:
        return {"active": False, "phase": "idle", "percent": 0, "message": ""}


def save_backup_config(
    *,
    enabled: bool | None = None,
    hour: int | None = None,
    minute: int | None = None,
) -> dict[str, Any]:
    conn = connect()
    try:
        if enabled is not None:
            set_setting(conn, SETTING_ENABLED, "true" if enabled else "false")
        if hour is not None:
            set_setting(conn, SETTING_HOUR, str(max(0, min(23, int(hour)))))
        if minute is not None:
            set_setting(conn, SETTING_MINUTE, str(max(0, min(59, int(minute)))))
        return load_backup_config(conn)
    finally:
        conn.close()


def _write_last_status(
    *,
    ok: bool,
    error: str = "",
    nbytes: int = 0,
    mark_run_date: bool = True,
) -> None:
    conn = connect()
    try:
        set_setting(conn, SETTING_LAST_OK, "1" if ok else "0")
        set_setting(conn, SETTING_LAST_AT, time.strftime("%Y-%m-%d %H:%M:%S"))
        set_setting(conn, SETTING_LAST_ERROR, (error or "")[:500])
        set_setting(conn, SETTING_LAST_BYTES, str(int(nbytes or 0)))
        if mark_run_date:
            set_setting(conn, SETTING_LAST_RUN_DATE, datetime.now().strftime("%Y-%m-%d"))
    finally:
        conn.close()


def _existing_tables(conn: Any) -> list[str]:
    found: list[str] = []
    with conn.cursor() as cur:
        for name in BACKUP_TABLES:
            cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
            row = cur.fetchone()
            if row and row[0]:
                found.append(name)
    return found


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return r"'\x" + bytes(value).hex() + "'"
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for v in value:
            if v is None:
                parts.append("NULL")
            elif isinstance(v, str):
                parts.append('"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"')
            else:
                parts.append(str(v))
        return "'{" + ",".join(parts) + "}'"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _run_python_dump(tables: list[str], dest_tmp: Path) -> None:
    """无 pg_dump 时的回退：按表导出 DELETE+INSERT（gzip）。

    使用服务端游标（named cursor）按批拉取，避免整表进客户端内存。
    """
    conn = connect_resource()
    try:
        # named cursor 必须在事务中；关闭自动提交
        try:
            conn.autocommit = False
        except Exception:
            pass
        with gzip.open(dest_tmp, "wt", encoding="utf-8", compresslevel=1) as gz:
            gz.write("-- sehuatang resource backup (python fallback)\n")
            gz.write("BEGIN;\n")
            for name in reversed(tables):
                gz.write(f"DELETE FROM {name};\n")
            for name in tables:
                # 每表独立命名游标，服务端流式
                cur = conn.cursor(name=f"bak_{name[:40]}")
                try:
                    cur.itersize = 500
                    cur.execute(f"SELECT * FROM {name}")
                    cols = [d[0] for d in cur.description] if cur.description else []
                    if not cols:
                        continue
                    col_sql = ", ".join(cols)
                    while True:
                        rows = cur.fetchmany(500)
                        if not rows:
                            break
                        for row in rows:
                            vals = ", ".join(_sql_literal(v) for v in row)
                            gz.write(f"INSERT INTO {name} ({col_sql}) VALUES ({vals});\n")
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
            gz.write("COMMIT;\n")
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()
    if not dest_tmp.is_file() or dest_tmp.stat().st_size < 32:
        dest_tmp.unlink(missing_ok=True)
        raise RuntimeError("备份文件为空或过小")


def _run_pg_dump(tables: list[str], dest_tmp: Path) -> None:
    if not tables:
        raise RuntimeError("没有可备份的资源表")
    dest_tmp.parent.mkdir(parents=True, exist_ok=True)
    if dest_tmp.exists():
        dest_tmp.unlink()

    if not shutil.which("pg_dump"):
        log.info("pg_dump not found · using python SQL dump fallback")
        _run_python_dump(tables, dest_tmp)
        return

    dsn = resource_dsn_kwargs()
    cmd = [
        "pg_dump",
        "-h",
        str(dsn["host"]),
        "-p",
        str(dsn["port"]),
        "-U",
        str(dsn["user"]),
        "-d",
        str(dsn["dbname"]),
        "--no-owner",
        "--no-acl",
        "--format=plain",
    ]
    for t in tables:
        cmd.extend(["--table", t])

    env = os.environ.copy()
    env["PGPASSWORD"] = str(dsn.get("password") or "")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert proc.stdout is not None
    try:
        with gzip.open(dest_tmp, "wb", compresslevel=1) as gz:
            shutil.copyfileobj(proc.stdout, gz, length=1024 * 256)
        stderr = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", errors="replace")
        code = proc.wait(timeout=3600)
    except Exception:
        proc.kill()
        raise
    if code != 0:
        if dest_tmp.exists():
            dest_tmp.unlink(missing_ok=True)
        err = (stderr or "").strip() or "unknown"
        # 客户端比服务端旧（如镜像里仍是 pg_dump 15、库是 16）时回退 Python 导出
        if "version mismatch" in err.lower():
            log.warning("pg_dump version mismatch · fallback to python dump: %s", err)
            _run_python_dump(tables, dest_tmp)
            return
        raise RuntimeError(f"pg_dump 失败 (exit {code}): {err}")
    if not dest_tmp.is_file() or dest_tmp.stat().st_size < 32:
        dest_tmp.unlink(missing_ok=True)
        raise RuntimeError("备份文件为空或过小")


async def _wait_crawler_idle(*, timeout: float = 90.0) -> bool:
    from workers.runner import crawl_status

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = crawl_status()
        if not st.get("running") and not st.get("looping"):
            return True
        await asyncio.sleep(0.5)
    return False


def _crawler_snapshot() -> dict[str, Any]:
    """快照所有已开爬虫开关的论坛 + 当前调度焦点（备份后按原样恢复）。"""
    from workers.runner import crawl_status

    conn = connect()
    try:
        focus = get_active_forum_id(conn)
        enabled_ids = enabled_crawler_forum_ids(conn)
    finally:
        conn.close()
    st = crawl_status()
    running_forum = str(st.get("forum_id") or "").strip() or focus
    return {
        "focus_forum_id": focus,
        "enabled_forum_ids": list(enabled_ids),
        "was_enabled": bool(enabled_ids),
        "was_looping": bool(st.get("looping")),
        "loop_kind": st.get("loop_kind"),
        "loop_forum_id": running_forum,
    }


async def _pause_crawler(snap: dict[str, Any]) -> None:
    """停止 runner，并关闭快照中所有已开论坛的爬虫开关。"""
    from workers.runner import _log_activity, crawl_status, stop_crawler

    st = crawl_status()
    enabled_ids = [str(x) for x in (snap.get("enabled_forum_ids") or []) if str(x).strip()]
    if snap.get("was_enabled") or st.get("running") or st.get("looping"):
        label = "、".join(enabled_ids) if enabled_ids else "运行中任务"
        _log_activity(f"备份：已暂停爬虫（{label}）")
        # disable=False：由本函数按多论坛快照关开关，避免只关焦点站
        await stop_crawler(disable=False, wait_seconds=12.0, force_after=8.0)

        if enabled_ids:
            conn = connect()
            try:
                configs = load_forum_configs_map(conn)
                for fid in enabled_ids:
                    if fid not in FULL_CRAWLER_FORUM_IDS:
                        continue
                    cfg = dict(configs.get(fid) or {})
                    if cfg.get("web_crawler_enabled"):
                        cfg["web_crawler_enabled"] = False
                        save_forum_config(conn, fid, cfg)
            finally:
                conn.close()

        idle = await _wait_crawler_idle(timeout=90.0)
        if not idle:
            raise RuntimeError("等待爬虫停止超时，取消备份")


async def _resume_crawler(snap: dict[str, Any], *, ok: bool) -> None:
    from workers.runner import _log_activity, start_continuous_loop

    enabled_ids = [str(x) for x in (snap.get("enabled_forum_ids") or []) if str(x).strip()]
    if not enabled_ids:
        return

    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        for fid in enabled_ids:
            if fid not in FULL_CRAWLER_FORUM_IDS:
                continue
            cfg = dict(configs.get(fid) or {})
            cfg["web_crawler_enabled"] = True
            save_forum_config(conn, fid, cfg)
    finally:
        conn.close()

    kind = snap.get("loop_kind")
    label = "备份完成" if ok else "备份失败"
    forums_label = "、".join(enabled_ids)
    if kind == "random_tid":
        from workers.random_tid import start_random_tid_loop

        start_random_tid_loop()
        _log_activity(f"{label}·已恢复随机抓帖 · 论坛开关 {forums_label}")
    else:
        start_continuous_loop()
        focus = str(snap.get("focus_forum_id") or snap.get("loop_forum_id") or "")
        _log_activity(
            f"{label}·已恢复连续调度 · 开关 {forums_label}"
            + (f" · 焦点 {focus}" if focus else "")
        )


async def run_backup_once(*, trigger: str = "manual") -> dict[str, Any]:
    """执行单份覆盖备份。trigger: manual | schedule。"""
    global _BUSY
    if not _LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "skipped": True,
            "reason": "busy",
            "error": "备份正在进行中，请稍候",
        }
    _BUSY = True
    snap: dict[str, Any] = {
        "was_enabled": False,
        "was_looping": False,
        "loop_kind": None,
        "enabled_forum_ids": [],
        "focus_forum_id": "",
    }
    backup_ok = False
    try:
        from workers.runner import _log_activity

        _log_activity(f"资源库备份开始 · {trigger}")
        snap = _crawler_snapshot()
        await _pause_crawler(snap)

        conn = connect_resource()
        try:
            tables = _existing_tables(conn)
        finally:
            conn.close()

        await asyncio.to_thread(_run_pg_dump, tables, BACKUP_TMP_PATH)
        os.replace(BACKUP_TMP_PATH, BACKUP_PATH)
        nbytes = int(BACKUP_PATH.stat().st_size)
        _write_last_status(ok=True, nbytes=nbytes, mark_run_date=True)
        _log_activity(f"资源库备份成功 · {nbytes} 字节 · {BACKUP_FILENAME}")
        backup_ok = True
        return {
            "ok": True,
            "trigger": trigger,
            "bytes": nbytes,
            "filename": BACKUP_FILENAME,
            "file": backup_file_info(),
            "tables": tables,
            "crawler_resumed": bool(snap.get("was_enabled")),
        }
    except Exception as exc:
        log.exception("backup failed")
        BACKUP_TMP_PATH.unlink(missing_ok=True)
        _write_last_status(ok=False, error=str(exc), mark_run_date=True)
        try:
            from workers.runner import _log_activity

            _log_activity(f"资源库备份失败 · {exc}")
        except Exception:
            pass
        return {
            "ok": False,
            "trigger": trigger,
            "error": str(exc),
            "file": backup_file_info(),
        }
    finally:
        try:
            await _resume_crawler(snap, ok=backup_ok)
        except Exception:
            log.exception("resume crawler after backup failed")
            try:
                from workers.runner import _log_activity

                _log_activity("备份后恢复爬虫失败，请在活动页手动开启")
            except Exception:
                pass
        _BUSY = False
        _LOCK.release()


async def _scheduler_loop() -> None:
    from workers.runner import _log_activity

    while True:
        try:
            await asyncio.sleep(60)
            if is_backup_busy():
                continue
            cfg = load_backup_config()
            if not cfg.get("enabled"):
                continue
            now = datetime.now()
            if now.hour != int(cfg["hour"]) or now.minute != int(cfg["minute"]):
                continue
            today = now.strftime("%Y-%m-%d")
            if cfg.get("last_run_date") == today:
                continue
            _log_activity("定时资源库备份触发")
            await run_backup_once(trigger="schedule")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("backup scheduler tick failed")


def start_backup_scheduler() -> asyncio.Task[None]:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return _SCHEDULER_TASK
    _SCHEDULER_TASK = asyncio.get_running_loop().create_task(_scheduler_loop())
    return _SCHEDULER_TASK


async def stop_backup_scheduler() -> None:
    global _SCHEDULER_TASK
    task = _SCHEDULER_TASK
    _SCHEDULER_TASK = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
