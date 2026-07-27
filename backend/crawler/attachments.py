"""下载并解析帖内附件：txt / zip·rar 内 txt·excel·doc · torrent→magnet。"""

from __future__ import annotations

import base64
import io
import logging
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from crawler.session import SessionManager
from parsers.attachments import (
    AttachmentFetchResult,
    DownloadAttachment,
    MAX_ARCHIVE_DEPTH,
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_THREAD,
    MAX_BINARY_LINK_SCAN_BYTES,
    extract_download_attachments,
    filter_all_link_attachments,
    filter_tail_attachments,
    filter_torrent_attachments,
    is_attachment_denied,
    is_attachment_login_required,
)
from parsers.torrent import parse_torrent_bytes

log = logging.getLogger(__name__)


def _bytes_over_limit(n: int, limit: int = MAX_ATTACHMENT_BYTES) -> bool:
    return int(n or 0) > int(limit)


def _skip_oversized(label: str, size: int, *, limit: int = MAX_ATTACHMENT_BYTES) -> bool:
    if not _bytes_over_limit(size, limit):
        return False
    log.info("Skip oversized %s (%s bytes > %s)", label, size, limit)
    return True


def _read_capped(data: bytes | None, *, label: str, limit: int) -> bytes | None:
    if data is None:
        return None
    if _skip_oversized(label, len(data), limit=limit):
        return None
    return data


def _decode_bytes(data: bytes) -> str:
    from parsers.safe_text import strip_nul

    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("latin-1", errors="ignore")
    return strip_nul(text)


def _rar_tool_candidates() -> list[str]:
    candidates = [
        shutil.which("unrar"),
        shutil.which("UnRAR"),
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files\WinRAR\rar.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        "/usr/local/bin/unrar",
    ]
    return [item for item in candidates if item and Path(item).exists()]


def _thread_author_name(html: str) -> str:
    """一楼作者名（常见作压缩包密码）。"""
    blob = html or ""
    m = re.search(
        r"""class=["']authi["'][^>]*>\s*<a[^>]*class=["'][^"']*\bxw1\b[^"']*["'][^>]*>\s*([^<]{1,40}?)\s*</a>""",
        blob,
        re.I,
    )
    if m:
        return re.sub(r"\s+", "", m.group(1)).strip()
    m = re.search(r"本帖最后由\s*([^\s<]{1,40})\s*于", blob)
    if m:
        return re.sub(r"\s+", "", m.group(1)).strip()
    return ""


def _archive_password_candidates(html: str) -> list[str]:
    """从一楼正文抽解压密码，并生成常见变体（空格/@/误粘扩展名）。

    正文未写密码时，补试楼主用户名（JapanHDV 等帖常见，tid 332436）。
    """
    from parsers.content import extract_password, parse_thread_content

    content = parse_thread_content(html or "")
    raw = (content.extract_password or "").strip()
    if not raw:
        # 标签拆开后「密码」与 www.98T.la@ 仍可能被漏抽，再扫一遍纯文本
        blob = f"{content.plain_text or ''}\n{content.blockcode_text or ''}"
        raw = (extract_password(blob) or "").strip()
    out: list[str] = []
    seen: set[str] = set()

    def _push(cand: str) -> None:
        c = (cand or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)

    if raw:
        variants = [
            raw,
            raw.replace(" ", ""),
            raw.replace("＠", "@"),
        ]
        # www.98T.la@ ↔ www.98T.la
        if raw.endswith("@") and len(raw) > 1:
            variants.append(raw[:-1].strip())
        elif "@" not in raw and "." in raw:
            variants.append(raw + "@")
        # CF 常把 MyBigDick@host 编成 MyBigDick@host.txt；实际解压不要 .txt
        for base in list(variants):
            low = base.lower()
            for suf in (".txt", ".rar", ".zip", ".7z", ".doc", ".docx"):
                if low.endswith(suf) and len(base) > len(suf) + 1:
                    variants.append(base[: -len(suf)].rstrip("."))
                    break
        for cand in variants:
            _push(cand)
    author = _thread_author_name(html or "")
    if author and author.lower() not in {"匿名", "游客", "guest"}:
        _push(author)
    return out


def _txt_names_in_archive(names: list[str]) -> list[str]:
    return [n for n in names if n and not n.endswith("/") and n.lower().endswith(".txt")]


def _excel_names_in_archive(names: list[str]) -> list[str]:
    return [
        n
        for n in names
        if n
        and not n.endswith("/")
        and n.lower().endswith((".xlsx", ".xlsm", ".xls", ".xlsb"))
    ]


def _csv_names_in_archive(names: list[str]) -> list[str]:
    return [
        n
        for n in names
        if n and not n.endswith("/") and n.lower().endswith(".csv")
    ]


def _is_torrent_filename(name: str) -> bool:
    """识别 .torrent；发帖截断常见 .torren（缺末尾 t）。"""
    return bool(re.search(r"\.torrent?$", (name or "").lower()))


def _torrent_names_in_archive(names: list[str]) -> list[str]:
    return [
        n
        for n in names
        if n and not n.endswith("/") and _is_torrent_filename(n)
    ]


def _doc_names_in_archive(names: list[str]) -> list[str]:
    return [
        n
        for n in names
        if n
        and not n.endswith("/")
        and n.lower().endswith((".doc", ".docx"))
    ]


def _link_member_names_in_archive(names: list[str]) -> list[str]:
    """压缩包内待试文件：txt → excel/csv → doc → torrent（逐个轮询）。"""
    return (
        _txt_names_in_archive(names)
        + _excel_names_in_archive(names)
        + _csv_names_in_archive(names)
        + _doc_names_in_archive(names)
        + _torrent_names_in_archive(names)
    )


def _text_has_importable_link(text: str) -> bool:
    low = (text or "").lower()
    return "magnet:" in low or "ed2k://" in low


def _pick_best_archive_texts(chunks: list[str]) -> str:
    """合并多文件语料：有 magnet/ed2k 的优先全保留；否则保留全部非空。"""
    cleaned = [c.strip() for c in chunks if c and c.strip()]
    if not cleaned:
        return ""
    with_links = [c for c in cleaned if _text_has_importable_link(c)]
    if with_links:
        return "\n\n".join(with_links)
    return "\n\n".join(cleaned)


def _push_member_text(member_texts: list[str], text: str) -> str | None:
    """追加成员语料；已含 magnet/ed2k 则返回合并结果供提前结束。"""
    if not (text or "").strip():
        return None
    member_texts.append(text)
    if _text_has_importable_link(text):
        return _pick_best_archive_texts(member_texts)
    return None


def _text_from_archive_member(name: str, data: bytes) -> str:
    lower = (name or "").lower()
    if _is_torrent_filename(name):
        magnet = parse_torrent_bytes(data, filename_hint=name)
        return magnet.link if magnet else ""
    if lower.endswith((".xlsx", ".xlsm", ".xls", ".xlsb")):
        return _extract_text_from_excel(data, name)
    if lower.endswith((".doc", ".docx")):
        return _extract_text_from_doc(data, name)
    if lower.endswith(".txt") or lower.endswith(".csv"):
        return _decode_bytes(data)
    return ""


def _nested_archive_members(names: list[str]) -> list[tuple[str, str]]:
    """压缩包内嵌套的 zip/rar → (name, kind)。"""
    out: list[tuple[str, str]] = []
    for name in names:
        if not name or name.endswith("/"):
            continue
        lower = name.lower()
        if lower.endswith(".zip"):
            out.append((name, "zip"))
        elif lower.endswith(".rar"):
            out.append((name, "rar"))
    return out


def _which_7z() -> str | None:
    found = (
        shutil.which("7z")
        or shutil.which("7z.exe")
        or shutil.which("7za")
        or shutil.which("7za.exe")
    )
    if found:
        return found
    for path in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if Path(path).exists():
            return path
    return None


def _extract_via_7z(
    data: bytes,
    passwords: list[str] | None = None,
    *,
    suffix: str,
    depth: int = 0,
) -> str:
    """用 7z 解出压缩包内全部 txt/excel；内层 zip/rar 用帖内密码逐个再解。"""
    if depth > MAX_ARCHIVE_DEPTH:
        return ""
    if _skip_oversized(f"7z archive depth={depth}", len(data or b"")):
        return ""
    seven = _which_7z()
    if not seven:
        return ""
    pwds = [p for p in (passwords or []) if p]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        arc_path = tmp_path / f"attach{suffix}"
        out_dir = tmp_path / "out"
        arc_path.write_bytes(data)
        attempts: list[list[str]] = [
            [seven, "x", "-y", f"-o{out_dir}", "-p-", str(arc_path)]
        ]
        for pwd in pwds:
            attempts.append(
                [seven, "x", "-y", f"-o{out_dir}", f"-p{pwd}", str(arc_path)]
            )
        for cmd in attempts:
            if out_dir.exists():
                shutil.rmtree(out_dir, ignore_errors=True)
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=45,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.debug("7z extract failed: %s", exc)
                continue
            if proc.returncode not in (0, 1):
                # 0=ok 1=warning；密码错多为非 0
                continue
            member_texts: list[str] = []
            for path in sorted(out_dir.rglob("*")):
                if not path.is_file():
                    continue
                suf = path.suffix.lower()
                if suf not in {
                    ".txt",
                    ".csv",
                    ".xlsx",
                    ".xlsm",
                    ".xls",
                    ".xlsb",
                    ".doc",
                    ".docx",
                    ".torrent",
                    ".torren",
                }:
                    continue
                try:
                    if _skip_oversized(
                        f"7z member {path.name}",
                        path.stat().st_size,
                        limit=MAX_ARCHIVE_MEMBER_BYTES,
                    ):
                        continue
                    raw_member = path.read_bytes()
                except OSError:
                    continue
                raw_member = _read_capped(
                    raw_member,
                    label=f"7z member {path.name}",
                    limit=MAX_ARCHIVE_MEMBER_BYTES,
                )
                if raw_member is None:
                    continue
                text = _text_from_archive_member(path.name, raw_member)
                early = _push_member_text(member_texts, text)
                if early:
                    return early
                if text.strip():
                    log.debug("7z member %s → %s chars", path.name, len(text))
            # 内层 zip/rar：逐个再解
            for path in sorted(out_dir.rglob("*")):
                if not path.is_file():
                    continue
                kind = (
                    "zip"
                    if path.suffix.lower() == ".zip"
                    else ("rar" if path.suffix.lower() == ".rar" else "")
                )
                if not kind:
                    continue
                try:
                    if _skip_oversized(
                        f"7z nested {path.name}",
                        path.stat().st_size,
                        limit=MAX_ATTACHMENT_BYTES,
                    ):
                        continue
                    nested = path.read_bytes()
                except OSError:
                    continue
                if len(nested) < 32:
                    continue
                nested = _read_capped(
                    nested, label=f"7z nested {path.name}", limit=MAX_ATTACHMENT_BYTES
                )
                if nested is None:
                    continue
                text = _extract_txt_from_archive(
                    nested, kind, passwords=pwds, depth=depth + 1
                )
                early = _push_member_text(member_texts, text)
                if early:
                    return early
            best = _pick_best_archive_texts(member_texts)
            if best.strip():
                return best
    return ""


def _zip_member_bytes(
    archive: Any,
    name: str,
    *,
    pwd: bytes | None = None,
    limit: int = MAX_ARCHIVE_MEMBER_BYTES,
) -> bytes | None:
    """读 zip 成员；按声明大小与解压后大小双重封顶，防 zip bomb。"""
    try:
        info = archive.getinfo(name)
        declared = int(getattr(info, "file_size", 0) or 0)
        if declared and _skip_oversized(f"zip member {name}", declared, limit=limit):
            return None
    except Exception:
        pass
    try:
        raw = archive.read(name, pwd=pwd) if pwd else archive.read(name)
    except Exception:
        return None
    return _read_capped(raw, label=f"zip member {name}", limit=limit)


def _extract_zip_pyzipper(
    data: bytes, passwords: list[str] | None = None, *, depth: int = 0
) -> str:
    """AES zip（stdlib 不解）优先走 pyzipper；支持内层 zip/rar。"""
    if depth > MAX_ARCHIVE_DEPTH:
        return ""
    if _skip_oversized(f"pyzipper archive depth={depth}", len(data or b"")):
        return ""
    try:
        import pyzipper
    except ImportError:
        return ""
    pwds = [p for p in (passwords or []) if p]
    for pwd in [None, *pwds]:
        try:
            with pyzipper.AESZipFile(io.BytesIO(data)) as archive:
                if pwd:
                    archive.setpassword(pwd.encode("utf-8"))
                names = archive.namelist()
                member_texts: list[str] = []
                for name in _link_member_names_in_archive(names):
                    raw_member = _zip_member_bytes(archive, name)
                    if raw_member is None:
                        continue
                    text = _text_from_archive_member(name, raw_member)
                    early = _push_member_text(member_texts, text)
                    if early:
                        return early
                for name, kind in _nested_archive_members(names):
                    nested = _zip_member_bytes(
                        archive, name, limit=MAX_ATTACHMENT_BYTES
                    )
                    if nested is None:
                        continue
                    text = _extract_txt_from_archive(
                        nested, kind, passwords=pwds, depth=depth + 1
                    )
                    early = _push_member_text(member_texts, text)
                    if early:
                        return early
                best = _pick_best_archive_texts(member_texts)
                if best.strip():
                    return best
        except Exception:
            continue
    return ""


def _extract_rar_text(
    data: bytes, passwords: list[str] | None = None, *, depth: int = 0
) -> str:
    if depth > MAX_ARCHIVE_DEPTH:
        return ""
    if _skip_oversized(f"rar archive depth={depth}", len(data or b"")):
        return ""
    pwds = [p for p in (passwords or []) if p]
    try:
        import rarfile
    except ImportError:
        log.debug("rarfile not installed, skip rar attachment")
        rarfile = None  # type: ignore[assignment]

    if rarfile is not None:
        tools = _rar_tool_candidates() or [None]
        for tool in tools:
            if tool:
                rarfile.UNRAR_TOOL = tool
            try:
                with rarfile.RarFile(io.BytesIO(data)) as archive:
                    names = archive.namelist()
                    for pwd in [None, *pwds]:
                        try:
                            if pwd:
                                archive.setpassword(pwd)
                            member_texts: list[str] = []
                            for name in _link_member_names_in_archive(names):
                                try:
                                    info = archive.getinfo(name)
                                    declared = int(getattr(info, "file_size", 0) or 0)
                                    if declared and _skip_oversized(
                                        f"rar member {name}",
                                        declared,
                                        limit=MAX_ARCHIVE_MEMBER_BYTES,
                                    ):
                                        continue
                                    raw_member = archive.read(name)
                                except Exception:
                                    continue
                                raw_member = _read_capped(
                                    raw_member,
                                    label=f"rar member {name}",
                                    limit=MAX_ARCHIVE_MEMBER_BYTES,
                                )
                                if raw_member is None:
                                    continue
                                text = _text_from_archive_member(name, raw_member)
                                early = _push_member_text(member_texts, text)
                                if early:
                                    return early
                            for name, kind in _nested_archive_members(names):
                                try:
                                    nested = archive.read(name)
                                except Exception:
                                    continue
                                nested = _read_capped(
                                    nested,
                                    label=f"rar nested {name}",
                                    limit=MAX_ATTACHMENT_BYTES,
                                )
                                if nested is None:
                                    continue
                                text = _extract_txt_from_archive(
                                    nested, kind, passwords=pwds, depth=depth + 1
                                )
                                early = _push_member_text(member_texts, text)
                                if early:
                                    return early
                            best = _pick_best_archive_texts(member_texts)
                            if best.strip():
                                return best
                            # 无密码时若已列全名仍读不出，再试密码
                            if not pwd and not archive.needs_password():
                                break
                        except Exception:
                            continue
            except Exception:
                continue

    text = _extract_via_7z(data, passwords=pwds, suffix=".rar", depth=depth)
    if text:
        return text
    if not (_which_7z() or _rar_tool_candidates()):
        log.info("RAR downloaded but no unrar/7z tool available")
    return ""


def _extract_zip_txt(
    data: bytes, passwords: list[str] | None = None, *, depth: int = 0
) -> str:
    if depth > MAX_ARCHIVE_DEPTH:
        return ""
    if _skip_oversized(f"zip archive depth={depth}", len(data or b"")):
        return ""
    pwds = [p for p in (passwords or []) if p]
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        log.info("Attachment is not a valid zip archive")
        return _extract_zip_pyzipper(data, passwords=pwds, depth=depth) or _extract_via_7z(
            data, passwords=pwds, suffix=".zip", depth=depth
        )
    try:
        names = archive.namelist()
        pwd_attempts: list[bytes | None] = [None]
        for p in pwds:
            for enc in ("utf-8", "gbk"):
                try:
                    b = p.encode(enc)
                except UnicodeEncodeError:
                    continue
                if b not in pwd_attempts:
                    pwd_attempts.append(b)
        member_texts: list[str] = []
        for name in _link_member_names_in_archive(names):
            for pwd in pwd_attempts:
                raw = _zip_member_bytes(archive, name, pwd=pwd)
                if raw is None:
                    continue
                text = _text_from_archive_member(name, raw)
                if text.strip():
                    # 同包多 .torrent：全部转磁力；txt/excel 仍可早停
                    if _is_torrent_filename(name):
                        member_texts.append(text)
                        break
                    early = _push_member_text(member_texts, text)
                    if early:
                        return early
                    break
        for name, kind in _nested_archive_members(names):
            for pwd in pwd_attempts:
                nested = _zip_member_bytes(
                    archive, name, pwd=pwd, limit=MAX_ATTACHMENT_BYTES
                )
                if nested is None:
                    continue
                text = _extract_txt_from_archive(
                    nested, kind, passwords=pwds, depth=depth + 1
                )
                if text.strip():
                    early = _push_member_text(member_texts, text)
                    if early:
                        return early
                    break
        best = _pick_best_archive_texts(member_texts)
        if best.strip():
            return best
    finally:
        archive.close()
    # ZipCrypto 失败，或 AES（stdlib 不解）→ pyzipper / 7z + 帖内密码
    return _extract_zip_pyzipper(data, passwords=pwds, depth=depth) or _extract_via_7z(
        data, passwords=pwds, suffix=".zip", depth=depth
    )


def _extract_txt_from_archive(
    data: bytes,
    kind: str,
    passwords: list[str] | None = None,
    *,
    depth: int = 0,
) -> str:
    if depth > MAX_ARCHIVE_DEPTH:
        return ""
    if _skip_oversized(f"{kind} archive depth={depth}", len(data or b"")):
        return ""
    if kind == "zip":
        return _extract_zip_txt(data, passwords=passwords, depth=depth)
    if kind == "rar":
        return _extract_rar_text(data, passwords=passwords, depth=depth)
    return ""


_LINK_IN_BINARY_RE = re.compile(
    r"(?:magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,60}[^\s\"'<>]*)"
    # ed2k 文件名常含空格/中文，不能用 [^\s]+ 截断
    r"|(?:ed2k://\|file\|[^\|]+\|\d+\|[A-Fa-f0-9]{32}\|/?)",
    re.I,
)


def _extract_text_from_xlsx_zip(data: bytes) -> str:
    """xlsx 实为 zip+xml：扫 XML 文本拼出单元格内容。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return ""
    chunks: list[str] = []
    try:
        for name in zf.namelist():
            lower = name.lower()
            if not (lower.endswith(".xml") or lower.endswith(".xml.rels")):
                continue
            if "xl/" not in lower:
                continue
            try:
                info = zf.getinfo(name)
                declared = int(getattr(info, "file_size", 0) or 0)
                if declared and _skip_oversized(
                    f"xlsx xml {name}",
                    declared,
                    limit=MAX_ARCHIVE_MEMBER_BYTES,
                ):
                    continue
                raw = zf.read(name)
            except Exception:
                continue
            raw = _read_capped(
                raw, label=f"xlsx xml {name}", limit=MAX_ARCHIVE_MEMBER_BYTES
            )
            if raw is None:
                continue
            text = _decode_bytes(raw)
            # 去掉标签，保留属性/文本里的 magnet、ed2k
            plain = re.sub(r"<[^>]+>", "\n", text)
            plain = re.sub(r"&amp;", "&", plain)
            plain = re.sub(r"&lt;", "<", plain)
            plain = re.sub(r"&gt;", ">", plain)
            plain = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), plain)
            if "magnet:" in plain.lower() or "ed2k://" in plain.lower():
                chunks.append(plain)
            else:
                # 仍保留有意义的非空行，便于其它解析
                lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
                if lines:
                    chunks.extend(lines[:2000])
    finally:
        zf.close()
    return "\n".join(chunks)


def _extract_text_from_excel_openpyxl(data: bytes) -> str:
    try:
        import openpyxl
    except ImportError:
        return ""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        log.debug("openpyxl load failed: %s", exc)
        return ""
    lines: list[str] = []
    try:
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell is None:
                        continue
                    s = str(cell).strip()
                    if s:
                        lines.append(s)
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return "\n".join(lines)


def _links_from_blob_text(blob: str) -> list[str]:
    found = _LINK_IN_BINARY_RE.findall(blob or "")
    out: list[str] = []
    for item in found:
        if isinstance(item, tuple):
            s = next((p for p in item if p), "")
        else:
            s = item
        s = (s or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _extract_links_from_binary_blob(data: bytes) -> str:
    """旧版 .xls / .doc 等二进制里直接扫 magnet/ed2k（ASCII + UTF-16LE）。"""
    from parsers.safe_text import strip_nul

    if not data:
        return ""
    # 超大二进制只扫头尾，避免 latin-1/utf-16 三份整文件解码撑爆内存
    scan = MAX_BINARY_LINK_SCAN_BYTES
    if len(data) > scan * 2:
        data = data[:scan] + data[-scan:]
    out: list[str] = []
    seen: set[str] = set()
    for blob in (
        data.decode("latin-1", errors="ignore"),
        data.decode("utf-16-le", errors="ignore"),
        data.decode("utf-16-be", errors="ignore"),
    ):
        for s in _links_from_blob_text(blob):
            cleaned = strip_nul(s)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
    return "\n".join(out)


def _xml_plain_text(xml: str) -> str:
    """去掉 XML/Word 标签，保留段落换行与实体解码。"""
    from parsers.safe_text import strip_nul

    plain = re.sub(r"</w:p>", "\n", xml or "", flags=re.I)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = re.sub(r"&amp;", "&", plain)
    plain = re.sub(r"&lt;", "<", plain)
    plain = re.sub(r"&gt;", ">", plain)

    def _entity_chr(m: re.Match[str]) -> str:
        try:
            code = int(m.group(1))
        except ValueError:
            return ""
        if code == 0:
            return ""
        try:
            return chr(code)
        except ValueError:
            return ""

    def _entity_hex(m: re.Match[str]) -> str:
        try:
            code = int(m.group(1), 16)
        except ValueError:
            return ""
        if code == 0:
            return ""
        try:
            return chr(code)
        except ValueError:
            return ""

    plain = re.sub(r"&#(\d+);", _entity_chr, plain)
    plain = re.sub(r"&#x([0-9a-fA-F]+);", _entity_hex, plain)
    return strip_nul(plain)


def _extract_text_from_docx(data: bytes) -> str:
    """OOXML .docx：读 word/*.xml 文本，并扫内嵌 magnet/ed2k。"""
    chunks: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return _extract_links_from_binary_blob(data)
    try:
        names = [
            n
            for n in zf.namelist()
            if n.lower().startswith("word/") and n.lower().endswith(".xml")
        ]
        # document.xml 优先
        names.sort(key=lambda n: (0 if n.lower().endswith("document.xml") else 1, n))
        for name in names:
            try:
                info = zf.getinfo(name)
                declared = int(getattr(info, "file_size", 0) or 0)
                if declared and _skip_oversized(
                    f"docx xml {name}",
                    declared,
                    limit=MAX_ARCHIVE_MEMBER_BYTES,
                ):
                    continue
                raw = zf.read(name)
            except Exception:
                continue
            raw = _read_capped(
                raw, label=f"docx xml {name}", limit=MAX_ARCHIVE_MEMBER_BYTES
            )
            if raw is None:
                continue
            plain = _xml_plain_text(_decode_bytes(raw))
            if plain.strip():
                chunks.append(plain)
    finally:
        zf.close()
    text = "\n".join(chunks).strip()
    binary_links = _extract_links_from_binary_blob(data)
    if binary_links and binary_links not in text:
        text = f"{text}\n{binary_links}".strip() if text else binary_links
    return text


def _extract_text_from_doc(data: bytes, filename: str = "") -> str:
    """从 Word 附件抽出文本 / 内嵌磁力·电驴。.docx 走 OOXML；.doc 扫二进制。"""
    if not data:
        return ""
    lower = (filename or "").lower()
    if lower.endswith(".docx") or data[:2] == b"PK":
        return _extract_text_from_docx(data)
    return _extract_links_from_binary_blob(data)


def _extract_text_from_excel(data: bytes, filename: str = "") -> str:
    """从 Excel 附件抽出单元格文本 / 内嵌磁力·电驴。"""
    if not data:
        return ""
    lower = (filename or "").lower()
    # OOXML
    if lower.endswith((".xlsx", ".xlsm", ".xlsb")) or data[:2] == b"PK":
        text = _extract_text_from_excel_openpyxl(data)
        if not text.strip():
            text = _extract_text_from_xlsx_zip(data)
        if text.strip():
            return text
    # 旧 BIFF .xls：二进制扫链；有 openpyxl 也读不了 xls
    binary_links = _extract_links_from_binary_blob(data)
    if binary_links.strip():
        return binary_links
    return ""


def _text_from_attachment_bytes(
    attachment: DownloadAttachment,
    data: bytes,
    passwords: list[str] | None = None,
) -> str:
    if not data:
        return ""
    if _skip_oversized(attachment.name or attachment.kind, len(data)):
        return ""
    if attachment.kind == "torrent":
        magnet = parse_torrent_bytes(data, filename_hint=attachment.name)
        return magnet.link if magnet else ""
    if attachment.kind in ("zip", "rar"):
        return _extract_txt_from_archive(data, attachment.kind, passwords=passwords)
    if attachment.kind == "excel":
        return _extract_text_from_excel(data, attachment.name)
    if attachment.kind == "doc":
        return _extract_text_from_doc(data, attachment.name)
    text = _decode_bytes(data)
    if "<html" in text.lower()[:200]:
        return ""
    return text


def _attachment_ui_suffix(attachment: DownloadAttachment) -> str:
    if attachment.kind == "torrent":
        return ".torrent"
    if attachment.kind in ("zip", "rar"):
        return f".{attachment.kind}"
    if attachment.kind == "excel":
        lower = (attachment.name or "").lower()
        for suf in (".xlsx", ".xlsm", ".xls", ".xlsb"):
            if lower.endswith(suf):
                return suf
        return ".xlsx"
    if attachment.kind == "doc":
        lower = (attachment.name or "").lower()
        if lower.endswith(".docx"):
            return ".docx"
        return ".doc"
    return ".txt"


def _thread_tid_key(url: str) -> str:
    """从帖 URL 抽可比较键（tid= / thread-N）。"""
    u = (url or "").strip()
    if not u:
        return ""
    m = re.search(r"[?&]tid=(\d+)", u, re.I)
    if m:
        return m.group(1)
    m = re.search(r"thread-(\d+)", u, re.I)
    if m:
        return m.group(1)
    return u.split("?", 1)[0].rstrip("/").lower()


class AttachmentDownloader:
    """基于已进站 SessionManager（Playwright 页）下载附件。"""

    def __init__(self, session: SessionManager):
        self.session = session

    async def ensure_thread_page(self, thread_url: str, *, timeout_ms: int = 60000) -> str:
        """确保浏览器在帖页。已在同一帖且附件区可见则跳过重复 goto（省 1～3s）。"""
        from parsers.thread_gates import looks_like_attachment_zone

        target_key = _thread_tid_key(thread_url)

        async def _try_reuse(page: Any) -> str | None:
            cur = (getattr(page, "url", None) or "") or ""
            if not target_key or _thread_tid_key(cur) != target_key:
                return None
            try:
                html = await page.content()
            except Exception:
                return None
            if html and len(html) > 1000 and looks_like_attachment_zone(html):
                log.info(
                    "attachments: already on tid=%s, skip reload (%s chars)",
                    target_key,
                    len(html),
                )
                return html
            return None

        try:
            reused = await self.session.run_on_page(_try_reuse)
            if reused:
                return reused
        except Exception as exc:
            log.debug("attachments: reuse page check failed: %s", exc)

        html = await self.session.fetch_html(thread_url, timeout_ms=timeout_ms)
        return html

    async def _fetch_bytes_via_page(
        self, url: str
    ) -> tuple[bytes | None, bool, bool]:
        """返回 (bytes, denied, login_required)。"""

        async def _on_page(page: Any) -> tuple[bytes | None, bool, bool]:
            try:
                # Content-Length / 实际体积超限则不 btoa，避免 2～3× 峰值
                result = await page.evaluate(
                    """
                    async ({ targetUrl, maxBytes }) => {
                        const resp = await fetch(targetUrl, { credentials: 'include' });
                        const contentType = resp.headers.get('content-type') || '';
                        const cl = resp.headers.get('content-length');
                        if (cl) {
                            const n = parseInt(cl, 10);
                            if (!Number.isNaN(n) && n > maxBytes) {
                                return {
                                    status: resp.status,
                                    contentType,
                                    body: '',
                                    skipped: 'too_large',
                                    size: n,
                                };
                            }
                        }
                        const buf = await resp.arrayBuffer();
                        if (buf.byteLength > maxBytes) {
                            return {
                                status: resp.status,
                                contentType,
                                body: '',
                                skipped: 'too_large',
                                size: buf.byteLength,
                            };
                        }
                        const bytes = new Uint8Array(buf);
                        let binary = '';
                        const chunk = 0x8000;
                        for (let i = 0; i < bytes.length; i += chunk) {
                            binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
                        }
                        return {
                            status: resp.status,
                            contentType,
                            body: btoa(binary),
                            size: bytes.length,
                        };
                    }
                    """,
                    {"targetUrl": url, "maxBytes": MAX_ATTACHMENT_BYTES},
                )
            except Exception as exc:
                log.debug("Attachment page fetch failed %s: %s", url, exc)
                return None, False, False

            if not result or result.get("status") != 200:
                return None, False, False

            if result.get("skipped") == "too_large":
                log.info(
                    "Attachment skipped (too large): %s (%s bytes)",
                    url,
                    result.get("size"),
                )
                return None, False, False

            content_type = (result.get("contentType") or "").lower()
            data = base64.b64decode(result.get("body") or "")
            if not data:
                return None, False, False
            if _skip_oversized(url, len(data)):
                return None, False, False

            if "text/html" in content_type or data.startswith(b"<!DOCTYPE") or data.startswith(b"<html"):
                # 提示页导航很长，登录/日限文案常在 8KB+；勿只看前 4KB
                html = _decode_bytes(data[:65536])
                if is_attachment_login_required(html):
                    log.info("Attachment login required: %s", url)
                    return None, False, True
                if is_attachment_denied(html):
                    log.info("Attachment denied: %s", url)
                    return None, True, False
                return None, False, False
            return data, False, False

        return await self.session.run_on_page(_on_page)

    async def _download_raw_via_ui(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        suffix: str,
    ) -> tuple[bytes | None, bool, bool]:
        """返回 (bytes, denied, login_required)。"""

        async def _on_page(page: Any) -> tuple[bytes | None, bool, bool]:
            from urllib.parse import parse_qs, unquote, urlparse

            locator = page.locator("a", has_text=attachment.name).first
            if await locator.count() == 0:
                aid = ""
                if "aid=" in (attachment.url or ""):
                    qs = parse_qs(urlparse(attachment.url).query)
                    aid = unquote((qs.get("aid") or [""])[0]).strip()
                    if not aid:
                        aid = unquote(attachment.url.split("aid=", 1)[-1].split("&", 1)[0])
                if aid:
                    # 完整 aid 过长时用前缀；勿截太短导致点到别的附件
                    needle = aid[:24] if len(aid) > 24 else aid
                    locator = page.locator(f"a[href*='attachment'][href*='{needle}']").first
            if await locator.count() == 0:
                return None, False, False

            # 无权弹窗很常见：下载事件常永不触发。先短等下载，再弹窗确认，
            # 避免每个附件空等满 timeout（可达 45–60s）才判无权。
            dl_ms = max(4000, min(int(timeout * 1000), 10000))
            popup_ms = max(5000, min(int(timeout * 1000), 12000))
            try:
                async with page.expect_download(timeout=dl_ms) as download_info:
                    await locator.click(timeout=5000)
                download = await download_info.value
                temp_path = Path(tempfile.gettempdir()) / f"sht-attach-{int(time.time() * 1000)}{suffix}"
                await download.save_as(temp_path)
                try:
                    size = temp_path.stat().st_size
                    if _skip_oversized(attachment.name or attachment.url, size):
                        return None, False, False
                    data = temp_path.read_bytes()
                finally:
                    temp_path.unlink(missing_ok=True)
                if data:
                    return data, False, False
            except Exception:
                pass

            popup = None
            try:
                async with page.expect_popup(timeout=popup_ms) as popup_info:
                    await locator.click(timeout=5000)
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded", timeout=popup_ms)
                html = await popup.content()
                if is_attachment_login_required(html):
                    log.info("Attachment popup login required: %s", attachment.name)
                    return None, False, True
                if is_attachment_denied(html):
                    log.info("Attachment popup denied: %s", attachment.name)
                    return None, True, False
                text = _decode_bytes(html.encode("utf-8", errors="ignore"))
                if suffix == ".torrent":
                    magnet = parse_torrent_bytes(
                        text.encode("utf-8", errors="ignore"),
                        filename_hint=attachment.name,
                    )
                    payload = magnet.link if magnet else ""
                elif "<html" in text.lower()[:200]:
                    payload = ""
                else:
                    payload = text
                if payload:
                    return payload.encode("utf-8", errors="ignore"), False, False
            except Exception as exc:
                log.debug("Attachment popup failed %s: %s", attachment.name, exc)
            finally:
                if popup is not None:
                    try:
                        await popup.close()
                    except Exception:
                        pass
                # 关掉同 context 残留页，避免长跑页面积压
                try:
                    for p in list(page.context.pages):
                        if p is not page:
                            await p.close()
                except Exception:
                    pass

            return None, False, False

        return await self.session.run_on_page(_on_page)

    async def _download_one(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        passwords: list[str] | None = None,
    ) -> tuple[str, bool, bool, bool]:
        """返回 (text, denied, downloaded, login_required)。"""
        denied = False
        login_required = False
        downloaded = False
        data, fetch_denied, fetch_login = await self._fetch_bytes_via_page(attachment.url)
        denied = denied or fetch_denied
        login_required = login_required or fetch_login
        if data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, data, passwords=passwords)
            if text.strip():
                return text, denied, downloaded, login_required

        # 页面直链已明确无权/需登录且无字节：UI 再点一次通常同样失败，省一轮
        if (fetch_denied or fetch_login) and not data:
            return "", fetch_denied, downloaded, fetch_login

        suffix = _attachment_ui_suffix(attachment)
        ui_data, ui_denied, ui_login = await self._download_raw_via_ui(
            attachment, timeout, suffix=suffix
        )
        denied = denied or ui_denied
        login_required = login_required or ui_login
        if ui_data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, ui_data, passwords=passwords)
            if text.strip():
                return text, denied, downloaded, login_required

        return "", denied, downloaded, login_required

    async def download_tail(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = MAX_ATTACHMENTS_PER_THREAD,
        timeout: float = 45,
        preferred_link: str | None = None,
    ) -> AttachmentFetchResult:
        """正文无链：按板块主链频次排序后逐个轮询附件。

        已抽到 magnet/ed2k 即停（判定够用）；115sha 等无目标链仍继续试下一附件。
        压缩包内同样：成员一旦含目标链即返回。
        """
        if not self.session._ready:
            return AttachmentFetchResult(failed=True)

        attachments = filter_all_link_attachments(
            extract_download_attachments(base_url, html),
            limit=max_files,
            preferred_link=preferred_link,
        )
        if not attachments:
            return AttachmentFetchResult()

        passwords = _archive_password_candidates(html)
        if passwords:
            log.info("Archive extract passwords from post: %s", passwords[0])

        chunks: list[str] = []
        any_denied = False
        any_login = False
        any_downloaded = False
        for attachment in attachments:
            try:
                text, denied, downloaded, login_required = await self._download_one(
                    attachment, timeout, passwords=passwords
                )
                if login_required:
                    any_login = True
                    log.info(
                        "Attachment %s login required — try next",
                        attachment.name,
                    )
                    continue
                if denied:
                    any_denied = True
                    # 无权限不代表整帖都不能下：继续试下一个（等待已缩短）
                    log.info(
                        "Attachment %s denied — try next",
                        attachment.name,
                    )
                    continue
                if downloaded:
                    any_downloaded = True
                if not text.strip():
                    log.info(
                        "Attachment %s (%s) yielded no text — continue next",
                        attachment.name,
                        attachment.kind,
                    )
                    continue
                chunks.append(text)
                if _text_has_importable_link(text):
                    log.info(
                        "Attachment %s (%s) → %s chars with magnet/ed2k — stop polling",
                        attachment.name,
                        attachment.kind,
                        len(text),
                    )
                    break
                log.info(
                    "Attachment %s (%s) → %s chars — continue polling",
                    attachment.name,
                    attachment.kind,
                    len(text),
                )
            except Exception as exc:
                log.warning("Attachment download failed %s: %s", attachment.name, exc)

        result_text = _pick_best_archive_texts(chunks)
        if result_text:
            # 已抽到可入库链接：即使部分附件无权/需登录也算成功
            return AttachmentFetchResult(
                text=result_text, downloaded=True, denied=False, login_required=False
            )
        # 登录提示页与用户组无权同一出路：denied → 占位「无权限下载附件」
        if any_login or any_denied:
            return AttachmentFetchResult(
                downloaded=any_downloaded,
                denied=True,
                login_required=any_login,
            )
        if any_downloaded:
            return AttachmentFetchResult(downloaded=True)
        return AttachmentFetchResult(failed=True)

    async def download_torrents(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = MAX_ATTACHMENTS_PER_THREAD,
        timeout: float = 45,
        preferred_link: str | None = None,
    ) -> AttachmentFetchResult:
        """与 download_tail 相同：全类型附件按板块频次逐个轮询。"""
        return await self.download_tail(
            html,
            base_url,
            max_files=max_files,
            timeout=timeout,
            preferred_link=preferred_link or "magnet",
        )


async def fetch_attachments_for_outcome(
    session: SessionManager,
    *,
    html: str,
    thread_url: str,
    attachment_kind: str,
    timeout: float = 45,
    preferred_link: str | None = None,
) -> AttachmentFetchResult:
    """按判定 kind 下载：txt_tail | torrent；轮询顺序跟板块主链。"""
    downloader = AttachmentDownloader(session)
    # 附件 UI 点击依赖当前 Playwright 页在帖子上；必须先导航到帖页。
    # 附件列表也优先用浏览器页 HTML：HTTP 语料常有附件区壳但 aid 与当前页不一致，
    # 会「找到附件却下失败」（BT种子帖成批「附件下载失败」的常见原因）。
    from parsers.thread_gates import looks_like_attachment_zone

    if not getattr(session, "_ready", False):
        try:
            await session.bootstrap(force=False)
        except Exception as exc:
            log.warning("Bootstrap session for attachments failed: %s", exc)

    page_html = ""
    try:
        page_html = await downloader.ensure_thread_page(thread_url)
    except Exception as exc:
        log.warning("Navigate to thread for attachments failed: %s", exc)

    http_ok = bool(html and len(html) > 8000 and looks_like_attachment_zone(html))
    page_ok = bool(
        page_html and len(page_html) > 1000 and looks_like_attachment_zone(page_html)
    )
    if page_ok:
        if html and html is not page_html:
            log.info(
                "attachments: use browser HTML for listing (http_zone=%s page_len=%s)",
                http_ok,
                len(page_html),
            )
        html = page_html
    elif (not http_ok) and page_html and len(page_html) > 1000:
        html = page_html

    # attachment_kind 仅作缺省主链提示；显式 preferred_link 优先
    link_pref = preferred_link
    if not link_pref:
        link_pref = "magnet" if attachment_kind == "torrent" else "ed2k"

    if attachment_kind == "torrent":
        return await downloader.download_torrents(
            html, thread_url, timeout=timeout, preferred_link=link_pref
        )
    if attachment_kind == "txt_tail":
        return await downloader.download_tail(
            html, thread_url, timeout=timeout, preferred_link=link_pref
        )
    return AttachmentFetchResult(failed=True)
