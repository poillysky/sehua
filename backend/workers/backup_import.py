"""将资源库备份（.sql.gz / .zip）合并导入现有库，按 hash / 标签名去重。"""

from __future__ import annotations

import gzip
import io
import logging
import re
import zipfile
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

_MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MiB


def extract_sql_text(raw: bytes, filename: str = "") -> str:
    """从上传字节中解出 SQL 文本，支持 .sql / .gz / .sql.gz / .zip。"""
    if not raw:
        raise ValueError("上传文件为空")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise ValueError(f"文件过大（上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")

    name = (filename or "").strip().lower()
    data = raw

    if name.endswith(".zip") or (len(data) >= 4 and data[:2] == b"PK"):
        data = _extract_from_zip(data)
        name = bk.BACKUP_FILENAME

    if name.endswith(".gz") or (len(data) >= 2 and data[:2] == b"\x1f\x8b"):
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise ValueError(f"无法解压 gzip：{exc}") from exc

    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            text = ""
    else:
        raise ValueError("无法解码备份 SQL")

    if not text.strip():
        raise ValueError("备份内容为空")
    return text


def _extract_from_zip(raw: bytes) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
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
    return zf.read(chosen)


def parse_backup_tables(sql: str) -> dict[str, list[dict[str, Any]]]:
    """解析备份 SQL → {table: [row_dict, ...]}。忽略 DELETE / DDL。"""
    tables: dict[str, list[dict[str, Any]]] = {}
    lines = sql.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("--"):
            i += 1
            continue

        copy_m = _COPY_RE.match(line)
        if copy_m:
            table = copy_m.group(1).lower()
            cols = [c.strip().strip('"').lower() for c in copy_m.group(2).split(",")]
            i += 1
            rows: list[dict[str, Any]] = []
            while i < len(lines):
                raw_line = lines[i]
                if raw_line == "\\." or raw_line.strip() == "\\.":
                    i += 1
                    break
                if raw_line.startswith("\\"):
                    i += 1
                    continue
                values = _parse_copy_row(raw_line, len(cols))
                rows.append(_row_dict(cols, values))
                i += 1
            if table not in _SKIP_TABLES:
                tables.setdefault(table, []).extend(rows)
            continue

        # 多行 INSERT 极少见；python dump 单行。兼容行末无分号的截断拼接。
        if line.upper().startswith("INSERT INTO"):
            buf = line
            while not buf.rstrip().endswith(";") and i + 1 < len(lines):
                i += 1
                buf += " " + lines[i].strip()
            ins = _INSERT_RE.match(buf.rstrip().rstrip(";").strip() + ";")
            if not ins:
                # 再试不带强制分号
                ins = _INSERT_RE.match(buf.strip())
            if ins:
                table = ins.group(1).lower()
                cols = [c.strip().strip('"').lower() for c in ins.group(2).split(",")]
                values = _parse_sql_values(ins.group(3))
                if table not in _SKIP_TABLES:
                    tables.setdefault(table, []).append(_row_dict(cols, values))
            i += 1
            continue

        i += 1
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
        # 数字 / 未加引号
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
    """若像 Postgres 文本数组字面量则解析为 list[str]，否则原样返回。"""
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
    """Postgres COPY text 格式：tab 分隔，\\N 为 NULL。"""
    parts = line.split("\t")
    # 允许列数略少（旧备份缺列）
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


def apply_backup_tables(conn: Any, tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """将解析后的表数据合并入库（去重）。"""
    stats = {
        "resources_inserted": 0,
        "resources_updated": 0,
        "resources_skipped": 0,
        "tags_upserted": 0,
        "resource_tags_linked": 0,
        "tables_seen": sorted(tables.keys()),
    }

    default_source = ensure_source(conn, "web:crawler", "网站爬虫", "web")
    source_cache: dict[int, int] = {}
    tag_id_map: dict[int, int] = {}  # backup tag_id → local tag_id
    tag_name_cache: dict[str, int] = {}

    # 1) tags：按 name 去重，建立旧 id → 新 id
    for row in tables.get("tags") or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        local_id = _ensure_tag(conn, name, tag_name_cache)
        stats["tags_upserted"] += 1
        old_id = row.get("id")
        if old_id is not None:
            try:
                tag_id_map[int(old_id)] = local_id
            except (TypeError, ValueError):
                pass
    conn.commit()

    # 2) 资源：ed2k_resources + resource_sources 按 hash 配对
    resources = {str(r.get("hash") or "").upper(): r for r in (tables.get("ed2k_resources") or []) if r.get("hash")}
    sources_by_hash = {
        str(r.get("hash") or "").upper(): r for r in (tables.get("resource_sources") or []) if r.get("hash")
    }

    for file_hash, res in resources.items():
        meta = sources_by_hash.get(file_hash) or {}
        filename = str(res.get("filename") or "").strip() or file_hash
        try:
            size = int(res.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        link = str(res.get("ed2k_link") or "").strip()
        if not link:
            stats["resources_skipped"] += 1
            continue

        existed_row = _existing_resource(conn, file_hash)
        existed = existed_row is not None
        if existed_row:
            old_filename, old_size, old_link = existed_row
            old_kind = infer_resource_link_kind(old_link)
            new_kind = infer_resource_link_kind(link)
            # 已有真实链接时，不让 stub 覆盖资源本体
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

        if (stats["resources_inserted"] + stats["resources_updated"]) % 200 == 0:
            conn.commit()

    # 仅有 resource_sources、无 ed2k_resources 行的异常备份：跳过（缺 FK）
    conn.commit()

    # 3) resource_tags：映射 tag_id 后 ON CONFLICT DO NOTHING
    for row in tables.get("resource_tags") or []:
        file_hash = str(row.get("hash") or "").upper()
        if not file_hash:
            continue
        old_tag = row.get("tag_id")
        local_tag: int | None = None
        if old_tag is not None:
            try:
                local_tag = tag_id_map.get(int(old_tag))
            except (TypeError, ValueError):
                local_tag = None
        if local_tag is None:
            # 若备份未带 tags 表，无法映射则跳过
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
    conn.commit()
    return stats


async def run_backup_import(*, raw: bytes, filename: str = "") -> dict[str, Any]:
    """暂停爬虫 → 解析备份 → 合并导入 → 恢复爬虫。与备份共用锁。"""
    if not bk._LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "skipped": True,
            "reason": "busy",
            "error": "备份或导入正在进行中，请稍候",
        }
    bk._BUSY = True
    snap: dict[str, Any] = {"was_enabled": False, "was_looping": False, "loop_kind": None}
    import_ok = False
    try:
        from workers.runner import _log_activity

        _log_activity(f"资源库备份导入开始 · {filename or 'upload'}")
        snap = bk._crawler_snapshot()
        await bk._pause_crawler(snap)

        sql = extract_sql_text(raw, filename)
        tables = parse_backup_tables(sql)
        if not tables.get("ed2k_resources") and not tables.get("resource_sources"):
            raise ValueError("备份中未找到资源表数据（ed2k_resources / resource_sources）")

        conn = connect_resource()
        try:
            stats = apply_backup_tables(conn, tables)
        finally:
            conn.close()

        import_ok = True
        _log_activity(
            "资源库备份导入成功 · "
            f"新增 {stats['resources_inserted']} · 更新 {stats['resources_updated']} · "
            f"跳过 {stats['resources_skipped']}"
        )
        return {"ok": True, "filename": filename or bk.BACKUP_FILENAME, **stats}
    except Exception as exc:
        log.exception("backup import failed")
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
        bk._LOCK.release()
