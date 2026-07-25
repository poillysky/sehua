"""将资源库备份（.sql.gz / .zip）合并导入现有库，按 hash / 标签名去重。

大备份走磁盘流式：上传落盘 → gzip 按行解压 → SQLite 中转 → 再写入资源库，
避免整份 SQL / 全表字典同时进内存（NAS 上否则容易 OOM）。
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from db.resource_db import connect_resource
from db.repository import ensure_source, infer_resource_link_kind, upsert_resource
from parsers.ed2k import Ed2kLink
from workers import backup as bk

log = logging.getLogger(__name__)

# 备份里可能带出的生成列，导入时跳过
_GENERATED_COLS = frozenset({"extension", "tsv"})

_SKIP_TABLES = frozenset({"import_jobs"})

_INSERT_RE = re.compile(
    r"^INSERT\s+INTO\s+(?:public\.)?([a-zA-Z_][\w]*)\s*\(([^)]+)\)\s*VALUES\s*\((.*)\)\s*;?\s*$",
    re.IGNORECASE,
)
_COPY_RE = re.compile(
    r"^COPY\s+(?:public\.)?([a-zA-Z_][\w]*)\s*\(([^)]+)\)\s+FROM\s+stdin\s*;?\s*$",
    re.IGNORECASE,
)

_MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MiB 压缩包上限
_UPLOAD_CHUNK = 1024 * 1024  # 1 MiB

# 导入进度（供管理端轮询）；与 backup._BUSY 共用锁语义
_PROGRESS_LOCK = threading.Lock()
_IMPORT_PROGRESS: dict[str, Any] = {
    "active": False,
    "phase": "idle",
    "percent": 0,
    "message": "",
    "filename": "",
    "processed": 0,
    "total": 0,
    "ok": None,
    "error": None,
    "stats": None,
    "started_at": None,
    "finished_at": None,
}


def get_import_progress() -> dict[str, Any]:
    with _PROGRESS_LOCK:
        return dict(_IMPORT_PROGRESS)


def _set_import_progress(**kwargs: Any) -> None:
    with _PROGRESS_LOCK:
        _IMPORT_PROGRESS.update(kwargs)


def _reset_import_progress(*, filename: str = "") -> None:
    _set_import_progress(
        active=True,
        phase="starting",
        percent=1,
        message="准备导入…",
        filename=filename or "",
        processed=0,
        total=0,
        ok=None,
        error=None,
        stats=None,
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        finished_at=None,
    )


def try_begin_import_job(filename: str = "") -> dict[str, Any] | None:
    """抢锁并标记忙碌；失败返回 None（已有备份/导入在跑）。"""
    if not bk._LOCK.acquire(blocking=False):
        return None
    bk._BUSY = True
    _reset_import_progress(filename=filename)
    return get_import_progress()


def abort_import_job(*, message: str = "") -> None:
    """上传落盘失败等：释放导入锁。"""
    _set_import_progress(
        active=False,
        phase="error",
        percent=100,
        message=message or "导入已取消",
        ok=False,
        error=message or "cancelled",
        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    bk._BUSY = False
    try:
        bk._LOCK.release()
    except RuntimeError:
        pass


def _phase_percent(phase: str, processed: int, total: int) -> int:
    """把阶段进度映射到整体 0–100。"""
    total = max(0, int(total or 0))
    processed = max(0, min(int(processed or 0), total if total else processed))
    frac = (processed / total) if total > 0 else 0.0
    ranges = {
        "starting": (1, 3),
        "pause": (3, 8),
        "extract": (8, 12),
        "parse": (12, 35),
        "tags": (35, 40),
        "resources": (40, 92),
        "resource_tags": (92, 98),
        "done": (100, 100),
        "error": (100, 100),
    }
    lo, hi = ranges.get(phase, (30, 90))
    if phase == "done":
        return 100
    return int(lo + (hi - lo) * frac)


def _import_workdir() -> Path:
    d = Path(bk.BACKUP_DIR) / "import-tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_upload_to_temp(
    *,
    filename: str,
    chunks: Iterator[bytes] | None = None,
    raw: bytes | None = None,
) -> Path:
    """把上传写到磁盘临时文件（不在内存里叠一份）。"""
    name = (filename or "upload.sql.gz").strip() or "upload.sql.gz"
    suffix = Path(name).suffix.lower() or ".bin"
    if name.lower().endswith(".sql.gz"):
        suffix = ".sql.gz"
    fd, path_s = tempfile.mkstemp(prefix="backup-up-", suffix=suffix, dir=str(_import_workdir()))
    path = Path(path_s)
    nbytes = 0
    try:
        with os.fdopen(fd, "wb") as out:
            if raw is not None:
                if len(raw) > _MAX_UPLOAD_BYTES:
                    raise ValueError(f"文件过大（上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")
                out.write(raw)
                nbytes = len(raw)
            else:
                assert chunks is not None
                for chunk in chunks:
                    if not chunk:
                        continue
                    nbytes += len(chunk)
                    if nbytes > _MAX_UPLOAD_BYTES:
                        raise ValueError(
                            f"文件过大（上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）"
                        )
                    out.write(chunk)
        if nbytes <= 0:
            raise ValueError("上传文件为空")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _prepare_sql_file(upload_path: Path, filename: str = "") -> tuple[Path, list[Path]]:
    """若是 zip，抽出内部 .sql/.sql.gz 到临时文件；返回 (工作文件, 需清理的额外路径)。"""
    owned: list[Path] = []
    name = (filename or upload_path.name).strip().lower()
    head = b""
    with upload_path.open("rb") as f:
        head = f.read(4)

    is_zip = name.endswith(".zip") or head[:2] == b"PK"
    if not is_zip:
        return upload_path, owned

    try:
        zf = zipfile.ZipFile(upload_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"无效的 zip：{exc}") from exc

    names = [n for n in zf.namelist() if not n.endswith("/")]
    if not names:
        raise ValueError("zip 内无文件")

    def rank(n: str) -> tuple[int, str]:
        lower = n.lower().replace("\\", "/")
        base = lower.rsplit("/", 1)[-1]
        if base == bk.BACKUP_FILENAME.lower():
            return (0, lower)
        if base.endswith(".sql.gz"):
            return (1, lower)
        if base.endswith(".gz"):
            return (2, lower)
        if base.endswith(".sql"):
            return (3, lower)
        return (9, lower)

    names.sort(key=rank)
    chosen = names[0]
    if rank(chosen)[0] >= 9:
        raise ValueError("zip 内未找到 .sql / .sql.gz 备份文件")

    base = Path(chosen).name
    suffix = ".sql.gz" if base.lower().endswith(".gz") else ".sql"
    fd, out_s = tempfile.mkstemp(prefix="backup-zip-", suffix=suffix, dir=str(_import_workdir()))
    out_path = Path(out_s)
    owned.append(out_path)
    try:
        with os.fdopen(fd, "wb") as out, zf.open(chosen) as src:
            while True:
                chunk = src.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        out_path.unlink(missing_ok=True)
        raise
    return out_path, owned


def iter_sql_lines(path: Path, filename: str = "") -> Iterator[str]:
    """按行流式读备份 SQL（gzip 边解压边读，不全量进内存）。"""
    _ = filename  # 兼容调用方；是否 gzip 看文件头
    with path.open("rb") as probe:
        head = probe.read(2)
    # 以文件头魔数为准（勿仅凭 .gz 后缀，避免误当 gzip 炸内存/报错）
    is_gz = head == b"\x1f\x8b"
    if is_gz:
        opener = gzip.open(path, mode="rt", encoding="utf-8", errors="replace")
    else:
        opener = path.open("rt", encoding="utf-8", errors="replace")
    with opener as text:
        for i, line in enumerate(text):
            if i and i % 4000 == 0:
                time.sleep(0)
            yield line.rstrip("\n\r")


def _emit_insert(buf: str) -> Iterator[tuple[str, dict[str, Any]]]:
    ins = _INSERT_RE.match(buf.rstrip().rstrip(";").strip() + ";")
    if not ins:
        ins = _INSERT_RE.match(buf.strip())
    if not ins:
        return
    table = ins.group(1).lower()
    if table in _SKIP_TABLES:
        return
    cols = [c.strip().strip('"').lower() for c in ins.group(2).split(",")]
    values = _parse_sql_values(ins.group(3))
    yield table, _row_dict(cols, values)


def iter_backup_rows_from_lines(lines: Iterator[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """从行迭代器产出 (table, row)，不缓存全表。"""
    pending: list[str] | None = None
    copy_table: str | None = None
    copy_cols: list[str] | None = None
    n = 0
    for line in lines:
        n += 1
        if pending is not None:
            pending.append(line.strip())
            buf = " ".join(pending)
            if not buf.rstrip().endswith(";"):
                continue
            pending = None
            yield from _emit_insert(buf)
            continue

        if copy_table is not None:
            raw_line = line
            if raw_line == "\\." or raw_line.strip() == "\\.":
                copy_table = None
                copy_cols = None
                continue
            if raw_line.startswith("\\"):
                continue
            assert copy_cols is not None
            if copy_table != "__skip__":
                values = _parse_copy_row(raw_line, len(copy_cols))
                yield copy_table, _row_dict(copy_cols, values)
            if n % 2000 == 0:
                time.sleep(0)
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        copy_m = _COPY_RE.match(stripped)
        if copy_m:
            table = copy_m.group(1).lower()
            cols = [c.strip().strip('"').lower() for c in copy_m.group(2).split(",")]
            if table in _SKIP_TABLES:
                copy_table = "__skip__"
                copy_cols = cols
            else:
                copy_table = table
                copy_cols = cols
            continue

        if stripped.upper().startswith("INSERT INTO"):
            if not stripped.rstrip().endswith(";"):
                pending = [stripped]
                continue
            yield from _emit_insert(stripped)
            continue


def extract_sql_text(raw: bytes, filename: str = "") -> str:
    """小样/测试用：整段解出 SQL。大文件请用流式路径，勿调用本函数。"""
    if not raw:
        raise ValueError("上传文件为空")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise ValueError(f"文件过大（上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")

    path = write_upload_to_temp(filename=filename or "t.sql.gz", raw=raw)
    owned: list[Path] = [path]
    try:
        work, extra = _prepare_sql_file(path, filename)
        owned.extend(extra)
        parts: list[str] = []
        for line in iter_sql_lines(work, filename):
            parts.append(line)
        text = "\n".join(parts)
        if not text.strip():
            raise ValueError("备份内容为空")
        return text
    finally:
        for p in owned:
            p.unlink(missing_ok=True)


def parse_backup_tables(sql: str) -> dict[str, list[dict[str, Any]]]:
    """解析备份 SQL → {table: [row_dict, ...]}（测试/小样；大备份勿用）。"""
    tables: dict[str, list[dict[str, Any]]] = {}
    for table, row in iter_backup_rows_from_lines(iter(sql.splitlines())):
        tables.setdefault(table, []).append(row)
    return tables


def _row_dict(cols: list[str], values: list[Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for idx, col in enumerate(cols):
        if col in _GENERATED_COLS:
            continue
        if idx < len(values):
            row[col] = values[idx]
    return row


def _parse_sql_values(payload: str) -> list[Any]:
    """解析 INSERT VALUES (...) 内的字面量列表。"""
    out: list[Any] = []
    i = 0
    n = len(payload)
    while i < n:
        while i < n and payload[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if payload[i : i + 4].upper() == "NULL" and (i + 4 >= n or payload[i + 4] in ", \t"):
            out.append(None)
            i += 4
            continue
        if payload[i : i + 4].upper() == "TRUE" and (i + 4 >= n or payload[i + 4] in ", \t"):
            out.append(True)
            i += 4
            continue
        if payload[i : i + 5].upper() == "FALSE" and (i + 5 >= n or payload[i + 5] in ", \t"):
            out.append(False)
            i += 5
            continue
        if payload[i] == "'":
            i += 1
            buf: list[str] = []
            while i < n:
                ch = payload[i]
                if ch == "'" and i + 1 < n and payload[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                if ch == "'":
                    i += 1
                    break
                buf.append(ch)
                i += 1
            text = "".join(buf)
            out.append(_decode_pg_array_or_text(text))
            continue
        j = i
        while j < n and payload[j] not in ",":
            j += 1
        token = payload[i:j].strip()
        i = j
        if re.fullmatch(r"-?\d+", token):
            out.append(int(token))
        elif re.fullmatch(r"-?\d+\.\d+", token):
            out.append(float(token))
        else:
            out.append(token)
    return out


def _decode_pg_array_or_text(text: str) -> Any:
    s = text.strip()
    if len(s) >= 2 and s[0] == "{" and s[-1] == "}":
        try:
            return _parse_pg_array(s)
        except ValueError:
            return text
    return text


def _parse_pg_array(literal: str) -> list[str | None]:
    inner = literal[1:-1]
    if not inner:
        return []
    items: list[str | None] = []
    i = 0
    n = len(inner)
    while i < n:
        while i < n and inner[i] in " \t":
            i += 1
        if i >= n:
            break
        if inner[i] == '"':
            i += 1
            buf: list[str] = []
            while i < n:
                ch = inner[i]
                if ch == "\\" and i + 1 < n:
                    buf.append(inner[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.append(ch)
                i += 1
            items.append("".join(buf))
        else:
            j = i
            while j < n and inner[j] != ",":
                j += 1
            token = inner[i:j].strip()
            items.append(None if token.upper() == "NULL" else token)
            i = j
        while i < n and inner[i] in " \t":
            i += 1
        if i < n and inner[i] == ",":
            i += 1
    return items


def _parse_copy_row(line: str, expected: int) -> list[Any]:
    parts = line.split("\t")
    values: list[Any] = []
    for p in parts:
        if p == "\\N":
            values.append(None)
        else:
            values.append(_unescape_copy(p))
    while len(values) < expected:
        values.append(None)
    return values[:expected]


def _unescape_copy(value: str) -> Any:
    if value.startswith("{") and value.endswith("}"):
        try:
            return _parse_pg_array(value)
        except ValueError:
            pass
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "\\": "\\"}
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    text = "".join(out)
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError:
            return text
    return text


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("{") and s.endswith("}"):
            try:
                arr = _parse_pg_array(s)
                return [str(v) for v in arr if v is not None]
            except ValueError:
                return [s]
        return [s]
    return [str(value)]


def _resolve_source_id(conn: Any, raw_id: Any, cache: dict[int, int], default_id: int) -> int:
    if raw_id is None:
        return default_id
    try:
        sid = int(raw_id)
    except (TypeError, ValueError):
        return default_id
    if sid in cache:
        return cache[sid]
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE id = %s", (sid,))
        row = cur.fetchone()
    if row:
        cache[sid] = int(row[0])
        return cache[sid]
    cache[sid] = default_id
    return default_id


def _existing_resource(conn: Any, file_hash: str) -> tuple[str, int, str] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename, size, ed2k_link FROM ed2k_resources WHERE hash = %s",
            (file_hash,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(row[0] or ""), int(row[1] or 0), str(row[2] or "")


def _ensure_tag(conn: Any, name: str, cache: dict[str, int]) -> int:
    key = (name or "").strip()
    if not key:
        raise ValueError("空标签名")
    if key in cache:
        return cache[key]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tags (name) VALUES (%s)
            ON CONFLICT (name) DO NOTHING
            """,
            (key,),
        )
        cur.execute("SELECT id FROM tags WHERE name = %s", (key,))
        tag_id = int(cur.fetchone()[0])
    cache[key] = tag_id
    return tag_id


def _json_dumps(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, default=str)


def spill_backup_to_sqlite(
    sql_path: Path,
    *,
    filename: str = "",
    spill_path: Path,
    on_progress: Any | None = None,
) -> dict[str, int]:
    """流式解析备份，行数据落到 SQLite，峰值内存约一行。"""

    def _prog(phase: str, processed: int, total: int, message: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(phase, processed, total, message)
        except Exception:
            pass

    if spill_path.exists():
        spill_path.unlink()
    spill = sqlite3.connect(str(spill_path))
    try:
        spill.execute("PRAGMA journal_mode=OFF")
        spill.execute("PRAGMA synchronous=OFF")
        spill.execute(
            "CREATE TABLE tags (ord INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
        )
        spill.execute(
            "CREATE TABLE ed2k_resources (hash TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        spill.execute(
            "CREATE TABLE resource_sources (hash TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        spill.execute(
            "CREATE TABLE resource_tags (ord INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
        )

        counts = {
            "tags": 0,
            "ed2k_resources": 0,
            "resource_sources": 0,
            "resource_tags": 0,
        }
        seen = 0
        _prog("parse", 0, 1, "流式解析备份到磁盘…")

        for table, row in iter_backup_rows_from_lines(iter_sql_lines(sql_path, filename)):
            if table == "tags":
                spill.execute("INSERT INTO tags(payload) VALUES (?)", (_json_dumps(row),))
                counts["tags"] += 1
            elif table == "ed2k_resources":
                h = str(row.get("hash") or "").upper()
                if not h:
                    continue
                row["hash"] = h
                spill.execute(
                    "INSERT OR REPLACE INTO ed2k_resources(hash, payload) VALUES (?, ?)",
                    (h, _json_dumps(row)),
                )
                counts["ed2k_resources"] += 1
            elif table == "resource_sources":
                h = str(row.get("hash") or "").upper()
                if not h:
                    continue
                row["hash"] = h
                spill.execute(
                    "INSERT OR REPLACE INTO resource_sources(hash, payload) VALUES (?, ?)",
                    (h, _json_dumps(row)),
                )
                counts["resource_sources"] += 1
            elif table == "resource_tags":
                spill.execute(
                    "INSERT INTO resource_tags(payload) VALUES (?)", (_json_dumps(row),)
                )
                counts["resource_tags"] += 1
            else:
                continue

            seen += 1
            if seen % 500 == 0:
                spill.commit()
                time.sleep(0)
                _prog(
                    "parse",
                    seen,
                    max(seen, 1),
                    f"已解析 {seen} 行 · 资源 {counts['ed2k_resources']}",
                )

        spill.commit()
        _prog(
            "parse",
            seen,
            max(seen, 1),
            f"解析完成 · 资源 {counts['ed2k_resources']} · 来源 {counts['resource_sources']}",
        )
        return counts
    finally:
        spill.close()


def _upsert_one_resource(
    conn: Any,
    *,
    res: dict[str, Any],
    meta: dict[str, Any],
    default_source: int,
    source_cache: dict[int, int],
    stats: dict[str, Any],
) -> None:
    file_hash = str(res.get("hash") or "").upper()
    filename = str(res.get("filename") or "").strip() or file_hash
    try:
        size = int(res.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    link = str(res.get("ed2k_link") or "").strip()
    if not link:
        stats["resources_skipped"] += 1
        return

    existed_row = _existing_resource(conn, file_hash)
    existed = existed_row is not None
    if existed_row:
        old_filename, old_size, old_link = existed_row
        old_kind = infer_resource_link_kind(old_link)
        new_kind = infer_resource_link_kind(link)
        if old_kind in {"ed2k", "magnet"} and new_kind == "stub":
            filename, size, link = old_filename, old_size, old_link

    ed2k = Ed2kLink(filename=filename, size=size, hash=file_hash, link=link)
    source_id = _resolve_source_id(conn, meta.get("source_id"), source_cache, default_source)
    upsert_resource(
        conn,
        ed2k,
        source_id,
        source_url=(str(meta["source_url"]) if meta.get("source_url") is not None else None),
        title=(str(meta["title"]) if meta.get("title") is not None else None),
        description=(str(meta["description"]) if meta.get("description") is not None else None),
        preview_images=_as_str_list(meta.get("preview_images")),
        ed2k_links=_as_str_list(meta.get("ed2k_links")),
        extract_password=(
            str(meta["extract_password"]) if meta.get("extract_password") is not None else None
        ),
        board_fid=(str(meta["board_fid"]) if meta.get("board_fid") is not None else None),
        board_name=(str(meta["board_name"]) if meta.get("board_name") is not None else None),
        forum_id=(str(meta["forum_id"]) if meta.get("forum_id") is not None else None),
        import_outcome=(
            str(meta["import_outcome"]) if meta.get("import_outcome") is not None else None
        ),
        commit=False,
    )
    if existed:
        stats["resources_updated"] += 1
    else:
        stats["resources_inserted"] += 1


def apply_from_spill(
    conn: Any,
    spill_path: Path,
    *,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """从磁盘中转库合并进资源库。"""

    def _prog(phase: str, processed: int, total: int, message: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(phase, processed, total, message)
        except Exception:
            pass

    spill = sqlite3.connect(str(spill_path))
    spill.row_factory = sqlite3.Row
    try:
        stats = {
            "resources_inserted": 0,
            "resources_updated": 0,
            "resources_skipped": 0,
            "tags_upserted": 0,
            "resource_tags_linked": 0,
            "tables_seen": [],
        }
        for t in ("tags", "ed2k_resources", "resource_sources", "resource_tags"):
            n = spill.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if n:
                stats["tables_seen"].append(t)

        default_source = ensure_source(conn, "web:crawler", "网站爬虫", "web")
        source_cache: dict[int, int] = {}
        tag_id_map: dict[int, int] = {}
        tag_name_cache: dict[str, int] = {}

        tag_total = int(spill.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
        _prog("tags", 0, max(tag_total, 1), "写入标签…")
        for i, row in enumerate(spill.execute("SELECT payload FROM tags ORDER BY ord"), 1):
            data = json.loads(row[0])
            name = str(data.get("name") or "").strip()
            if not name:
                continue
            local_id = _ensure_tag(conn, name, tag_name_cache)
            stats["tags_upserted"] += 1
            old_id = data.get("id")
            if old_id is not None:
                try:
                    tag_id_map[int(old_id)] = local_id
                except (TypeError, ValueError):
                    pass
            if i == tag_total or i % 50 == 0:
                _prog("tags", i, tag_total, f"标签 {i}/{tag_total}")
        conn.commit()

        total_res = int(spill.execute("SELECT COUNT(*) FROM ed2k_resources").fetchone()[0])
        _prog("resources", 0, max(total_res, 1), f"合并资源 0/{total_res}")
        done_res = 0
        for row in spill.execute("SELECT hash, payload FROM ed2k_resources"):
            file_hash = str(row[0] or "").upper()
            res = json.loads(row[1])
            src_row = spill.execute(
                "SELECT payload FROM resource_sources WHERE hash = ?",
                (file_hash,),
            ).fetchone()
            meta = json.loads(src_row[0]) if src_row else {}
            _upsert_one_resource(
                conn,
                res=res,
                meta=meta,
                default_source=default_source,
                source_cache=source_cache,
                stats=stats,
            )
            done_res += 1
            if (stats["resources_inserted"] + stats["resources_updated"]) % 200 == 0:
                conn.commit()
                time.sleep(0)
            if done_res == total_res or done_res % 200 == 0:
                _prog("resources", done_res, total_res, f"合并资源 {done_res}/{total_res}")
        conn.commit()

        tag_link_total = int(spill.execute("SELECT COUNT(*) FROM resource_tags").fetchone()[0])
        _prog("resource_tags", 0, max(tag_link_total, 1), "关联标签…")
        for i, row in enumerate(spill.execute("SELECT payload FROM resource_tags ORDER BY ord"), 1):
            data = json.loads(row[0])
            file_hash = str(data.get("hash") or "").upper()
            if not file_hash:
                continue
            old_tag = data.get("tag_id")
            local_tag: int | None = None
            if old_tag is not None:
                try:
                    local_tag = tag_id_map.get(int(old_tag))
                except (TypeError, ValueError):
                    local_tag = None
            if local_tag is None:
                continue
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO resource_tags (hash, tag_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (file_hash, local_tag),
                )
                if cur.rowcount:
                    stats["resource_tags_linked"] += 1
            if i == tag_link_total or i % 500 == 0:
                _prog("resource_tags", i, tag_link_total, f"关联标签 {i}/{tag_link_total}")
        conn.commit()
        _prog("done", total_res, total_res, "合并完成")
        return stats
    finally:
        spill.close()


def apply_backup_tables(
    conn: Any,
    tables: dict[str, list[dict[str, Any]]],
    *,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """兼容测试：内存表 → 临时 spill → apply_from_spill。"""
    fd, spill_s = tempfile.mkstemp(prefix="backup-mem-", suffix=".sqlite", dir=str(_import_workdir()))
    os.close(fd)
    spill_path = Path(spill_s)
    try:
        spill = sqlite3.connect(str(spill_path))
        try:
            spill.execute(
                "CREATE TABLE tags (ord INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
            )
            spill.execute(
                "CREATE TABLE ed2k_resources (hash TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            spill.execute(
                "CREATE TABLE resource_sources (hash TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            spill.execute(
                "CREATE TABLE resource_tags (ord INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
            )
            for row in tables.get("tags") or []:
                spill.execute("INSERT INTO tags(payload) VALUES (?)", (_json_dumps(row),))
            for row in tables.get("ed2k_resources") or []:
                h = str(row.get("hash") or "").upper()
                if not h:
                    continue
                row = dict(row)
                row["hash"] = h
                spill.execute(
                    "INSERT OR REPLACE INTO ed2k_resources(hash, payload) VALUES (?, ?)",
                    (h, _json_dumps(row)),
                )
            for row in tables.get("resource_sources") or []:
                h = str(row.get("hash") or "").upper()
                if not h:
                    continue
                row = dict(row)
                row["hash"] = h
                spill.execute(
                    "INSERT OR REPLACE INTO resource_sources(hash, payload) VALUES (?, ?)",
                    (h, _json_dumps(row)),
                )
            for row in tables.get("resource_tags") or []:
                spill.execute(
                    "INSERT INTO resource_tags(payload) VALUES (?)", (_json_dumps(row),)
                )
            spill.commit()
        finally:
            spill.close()
        return apply_from_spill(conn, spill_path, on_progress=on_progress)
    finally:
        spill_path.unlink(missing_ok=True)


def _sync_merge_backup(
    *,
    path: str | Path | None = None,
    raw: bytes | None = None,
    filename: str = "",
    on_progress: Any | None = None,
    cleanup_upload: bool = False,
) -> dict[str, Any]:
    """磁盘流式：解压解析中转 → 写库（须在线程里跑）。"""

    def _on(phase: str, processed: int, total: int, message: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(phase, processed, total, message)
        except Exception:
            pass

    owned: list[Path] = []
    upload: Path | None = None
    try:
        if path is not None:
            upload = Path(path)
        else:
            if not raw:
                raise ValueError("上传文件为空")
            upload = write_upload_to_temp(filename=filename or "upload.sql.gz", raw=raw)
            owned.append(upload)
            raw = None  # noqa: F841 — 尽快丢掉大字节引用

        _on("extract", 0, 1, "准备备份文件…")
        work, extra = _prepare_sql_file(upload, filename)
        owned.extend(extra)

        fd, spill_s = tempfile.mkstemp(
            prefix="backup-spill-", suffix=".sqlite", dir=str(_import_workdir())
        )
        os.close(fd)
        spill_path = Path(spill_s)
        owned.append(spill_path)

        counts = spill_backup_to_sqlite(
            work, filename=filename, spill_path=spill_path, on_progress=on_progress
        )
        if counts["ed2k_resources"] <= 0 and counts["resource_sources"] <= 0:
            raise ValueError("备份中未找到资源表数据（ed2k_resources / resource_sources）")

        # 解析完成后即可删压缩包，腾出磁盘与页缓存压力
        if cleanup_upload and upload is not None:
            try:
                upload.unlink(missing_ok=True)
                if upload in owned:
                    owned.remove(upload)
            except Exception:
                pass
        for p in list(extra):
            if p != work:
                p.unlink(missing_ok=True)

        n_res = counts["ed2k_resources"]
        _on("resources", 0, max(n_res, 1), f"开始合并 {n_res} 条资源…")

        conn = connect_resource()
        try:
            return apply_from_spill(conn, spill_path, on_progress=on_progress)
        finally:
            conn.close()
    finally:
        for p in owned:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        if cleanup_upload and path is not None:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass


async def run_backup_import(
    *,
    raw: bytes | None = None,
    path: str | Path | None = None,
    filename: str = "",
    hold_lock: bool = False,
    cleanup_upload: bool = False,
) -> dict[str, Any]:
    """暂停爬虫 → 流式解析合并 → 恢复爬虫。与备份共用锁。"""
    if not hold_lock:
        if not bk._LOCK.acquire(blocking=False):
            return {
                "ok": False,
                "skipped": True,
                "reason": "busy",
                "error": "备份或导入正在进行中，请稍候",
            }
        bk._BUSY = True
        _reset_import_progress(filename=filename)

    snap: dict[str, Any] = {"was_enabled": False, "was_looping": False, "loop_kind": None}
    import_ok = False
    stats: dict[str, Any] = {}

    def _on_apply(phase: str, processed: int, total: int, message: str) -> None:
        _set_import_progress(
            phase=phase,
            processed=processed,
            total=total,
            message=message,
            percent=_phase_percent(phase, processed, total),
            active=True,
        )

    try:
        from workers.runner import _log_activity

        _log_activity(f"资源库备份导入开始 · {filename or 'upload'}")
        _set_import_progress(
            phase="pause",
            percent=_phase_percent("pause", 0, 1),
            message="暂停爬虫…",
            active=True,
        )
        snap = bk._crawler_snapshot()
        await bk._pause_crawler(snap)

        stats = await asyncio.to_thread(
            lambda: _sync_merge_backup(
                path=path,
                raw=raw,
                filename=filename,
                on_progress=_on_apply,
                cleanup_upload=cleanup_upload,
            )
        )

        import_ok = True
        _set_import_progress(
            active=False,
            phase="done",
            percent=100,
            message=(
                f"导入完成 · 新增 {stats['resources_inserted']} · "
                f"更新 {stats['resources_updated']} · 跳过 {stats['resources_skipped']}"
            ),
            ok=True,
            error=None,
            stats=stats,
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        _log_activity(
            "资源库备份导入成功 · "
            f"新增 {stats['resources_inserted']} · 更新 {stats['resources_updated']} · "
            f"跳过 {stats['resources_skipped']}"
        )
        return {"ok": True, "filename": filename or bk.BACKUP_FILENAME, **stats}
    except Exception as exc:
        log.exception("backup import failed")
        _set_import_progress(
            active=False,
            phase="error",
            percent=100,
            message=f"导入失败：{exc}",
            ok=False,
            error=str(exc),
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            from workers.runner import _log_activity

            _log_activity(f"资源库备份导入失败 · {exc}")
        except Exception:
            pass
        return {
            "ok": False,
            "filename": filename or bk.BACKUP_FILENAME,
            "error": str(exc),
        }
    finally:
        try:
            await bk._resume_crawler(snap, ok=import_ok)
        except Exception:
            log.exception("resume crawler after backup import failed")
            try:
                from workers.runner import _log_activity

                _log_activity("导入后恢复爬虫失败，请在活动页手动开启")
            except Exception:
                pass
        bk._BUSY = False
        try:
            bk._LOCK.release()
        except RuntimeError:
            pass


async def run_backup_import_background(
    *,
    path: str | Path | None = None,
    raw: bytes | None = None,
    filename: str = "",
    cleanup_upload: bool = False,
) -> None:
    """供 API 在已抢锁后投递的后台任务。"""
    await run_backup_import(
        path=path,
        raw=raw,
        filename=filename,
        hold_lock=True,
        cleanup_upload=cleanup_upload,
    )
