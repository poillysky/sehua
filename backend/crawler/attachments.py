"""下载并解析帖内附件：txt / zip·rar 内 txt·excel·doc · torrent→magnet。"""

from __future__ import annotations

import asyncio
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
    is_attachment_download_limited,
    is_attachment_login_required,
    is_attachment_not_found,
    is_directory_tree_attachment_name,
    listing_shows_attach_denied,
)
from parsers.torrent import parse_torrent_bytes

log = logging.getLogger(__name__)

# 多附件防卡死：总墙钟 / 单附件 / 浏览器页操作 / Flare / 解压
ATTACH_POLL_WALL_SEC = 180.0
ATTACH_ONE_WALL_SEC = 55.0
ATTACH_PAGE_OP_SEC = 30.0
ATTACH_FLARE_HTTP_SEC = 35.0
ATTACH_FLARE_MAX_TIMEOUT_MS = 25_000
ATTACH_EXTRACT_SEC = 45.0
# 连续空/超时多少次后停（多附件空转早停）
ATTACH_EMPTY_STREAK_STOP = 3
# 压缩包内最多尝试的链文件成员（防巨型目录包拖死）
MAX_ARCHIVE_LINK_MEMBERS = 40
MAX_NESTED_ARCHIVES_PER_LEVEL = 8


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
    ordered = (
        _txt_names_in_archive(names)
        + _excel_names_in_archive(names)
        + _csv_names_in_archive(names)
        + _doc_names_in_archive(names)
        + _torrent_names_in_archive(names)
    )
    if len(ordered) > MAX_ARCHIVE_LINK_MEMBERS:
        log.info(
            "Archive has %s link members — only try first %s",
            len(ordered),
            MAX_ARCHIVE_LINK_MEMBERS,
        )
        return ordered[:MAX_ARCHIVE_LINK_MEMBERS]
    return ordered


def _text_has_importable_link(text: str) -> bool:
    low = (text or "").lower()
    return "magnet:" in low or "ed2k://" in low


def _count_importable_links(text: str) -> int:
    """语料中可入库链数（ed2k hash / magnet btih 去重）。"""
    raw = text or ""
    if not raw.strip():
        return 0
    hashes: set[str] = set()
    for m in re.finditer(r"ed2k://[^\s\"'<>]+", raw, re.I):
        hm = re.search(r"\|([A-Fa-f0-9]{32})\|", m.group(0))
        if hm:
            hashes.add("e:" + hm.group(1).upper())
    for m in re.finditer(r"btih:([A-Fa-f0-9]{40})", raw, re.I):
        hashes.add("m:" + m.group(1).upper())
    return len(hashes)


def _quota_expect_from_html(html: str) -> int | None:
    """从帖标题/一楼取 N配额，供多 txt 附件合并时对照。"""
    blob = html or ""
    parts: list[str] = []
    for pat in (
        r'id=["\']thread_subject["\'][^>]*>(.*?)</',
        r"<title[^>]*>([^<]+)</title>",
        r'id=["\']postmessage_\d+["\'][^>]*>([\s\S]*?)</div>',
    ):
        m = re.search(pat, blob, re.I)
        if m:
            parts.append(re.sub(r"<[^>]+>", " ", m.group(1)))
    try:
        from parsers.resource_frame import _title_quota_count

        return _title_quota_count("\n".join(parts))
    except Exception:
        m = re.search(r"(\d+)\s*配额", "\n".join(parts))
        return int(m.group(1)) if m else None


def _pick_best_archive_texts(chunks: list[str]) -> str:
    """合并多文件语料：有 magnet/ed2k 的优先全保留；否则保留全部非空。"""
    cleaned = [c.strip() for c in chunks if c and c.strip()]
    if not cleaned:
        return ""
    with_links = [c for c in cleaned if _text_has_importable_link(c)]
    if with_links:
        return "\n\n".join(with_links)
    return "\n\n".join(cleaned)


def _attach_merge_still_unqualified(
    html: str,
    attach_text: str,
    *,
    preferred_link: str | None = None,
    base_url: str = "",
) -> bool:
    """试算合并附件后是否仍不合格 → True 则必须继续下一个附件。

    硬规则：不合格就逐个判完；仅明确合格（outcome 不以「不合格」开头）才可停。
    无链 / 试算失败 / 异常 → 一律当作仍不合格，继续轮询（勿因预览异常提前停）。
    """
    if not (attach_text or "").strip():
        return True
    try:
        from db.persist import preview_frame_outcome
        from parsers.attachments import inject_attachment_text
        from parsers.links import parse_thread_dual

        pref = (preferred_link or "both").strip().lower()
        if pref not in {"magnet", "ed2k", "both"}:
            pref = "both"
        html2 = inject_attachment_text(html or "", attach_text)
        parsed = parse_thread_dual(
            html2,
            preferred_link=pref,  # type: ignore[arg-type]
            extra_text=attach_text,
            base_url=base_url or "",
        )
        if not parsed.assets:
            return True
        parsed.had_attachments = True
        out = preview_frame_outcome(
            parsed, import_outcome="成功：附件目标链接"
        )
        if not out:
            return True
        return out.startswith("不合格")
    except Exception as exc:
        log.warning("attach merge preview failed — treat as 不合格, continue: %s", exc)
        return True


def _push_member_text(member_texts: list[str], text: str) -> None:
    """追加非空成员语料。

    同包多 txt/excel/torrent 必须全部合并后再返回（tid=2204368：分卷 993+137≈1131配额；
    早停会只拿到第一份「不全」txt 误判漏链）。
    """
    if (text or "").strip():
        member_texts.append(text)


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
                _push_member_text(member_texts, text)
                if text.strip():
                    log.debug("7z member %s → %s chars", path.name, len(text))
            # 内层 zip/rar：逐个再解（封顶，防嵌套爆炸）
            nested_n = 0
            for path in sorted(out_dir.rglob("*")):
                if nested_n >= MAX_NESTED_ARCHIVES_PER_LEVEL:
                    break
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
                nested_n += 1
                text = _extract_txt_from_archive(
                    nested, kind, passwords=pwds, depth=depth + 1
                )
                _push_member_text(member_texts, text)
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
                    _push_member_text(member_texts, text)
                for name, kind in _nested_archive_members(names)[
                    :MAX_NESTED_ARCHIVES_PER_LEVEL
                ]:
                    nested = _zip_member_bytes(
                        archive, name, limit=MAX_ATTACHMENT_BYTES
                    )
                    if nested is None:
                        continue
                    text = _extract_txt_from_archive(
                        nested, kind, passwords=pwds, depth=depth + 1
                    )
                    _push_member_text(member_texts, text)
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
                                _push_member_text(member_texts, text)
                            for name, kind in _nested_archive_members(names)[
                                :MAX_NESTED_ARCHIVES_PER_LEVEL
                            ]:
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
                                _push_member_text(member_texts, text)
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
                    # 同包多 txt/excel/torrent：全部合并（分卷勿早停）
                    _push_member_text(member_texts, text)
                    break
        for name, kind in _nested_archive_members(names)[:MAX_NESTED_ARCHIVES_PER_LEVEL]:
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
                    _push_member_text(member_texts, text)
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


def _html_is_cf_challenge(html: str) -> bool:
    try:
        from crawler.cf_bypass import is_cf_challenge

        return bool(html) and is_cf_challenge(html)
    except Exception:
        return False


class AttachmentDownloader:
    """基于已进站 SessionManager（Playwright 页）下载附件。"""

    def __init__(self, session: SessionManager):
        self.session = session
        # 同帖第一次 Flare 无收获后，后续附件不再打 Flare（省串行等待）
        self._skip_flare = False

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
            # CF 挑战页勿当复用成功（否则会「看得到附件区壳却下不了」）
            if (
                html
                and len(html) > 1000
                and looks_like_attachment_zone(html)
                and not _html_is_cf_challenge(html)
            ):
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

    def _fetch_bytes_via_flare(
        self, url: str
    ) -> tuple[bytes | None, bool, bool, bool, bool]:
        """经 FlareSolverr 同出口拉附件（Playwright 无 cf_clearance 时的回退）。

        文本附件（ed2k txt）最稳；二进制种子可能被 Flare 当文本损坏，仍作尽力而为。
        返回同 _fetch_bytes_via_page：(bytes, denied, login_required, daily_limited, empty)。
        """
        from crawler.cf_bypass import flaresolverr_get, resolve_flaresolverr_url

        api = resolve_flaresolverr_url()
        if not api:
            return None, False, False, False, False
        cookies = dict(getattr(self.session, "cookies", {}) or {})
        proxy = str(getattr(self.session, "proxy", "") or "").strip()
        try:
            solution = flaresolverr_get(
                api,
                url,
                cookies=cookies,
                proxy=proxy,
                timeout=ATTACH_FLARE_HTTP_SEC,
                max_timeout_ms=ATTACH_FLARE_MAX_TIMEOUT_MS,
            )
        except Exception as exc:
            log.warning("FlareSolverr attach fetch error %s: %s", url, exc)
            return None, False, False, False, False
        if not solution:
            return None, False, False, False, False

        for c in solution.get("cookies") or []:
            name = str(c.get("name") or "").strip()
            value = c.get("value")
            if name and value is not None:
                self.session.cookies[name] = str(value)
        ua = solution.get("userAgent")
        if ua:
            self.session.user_agent = str(ua)

        body = solution.get("response") or ""
        if not body:
            return None, False, False, False, True
        if _html_is_cf_challenge(body):
            log.warning("FlareSolverr attach still CF: %s", url)
            return None, False, False, False, False
        if SessionManager.is_safe_shell(body):
            log.warning("FlareSolverr attach hit R18 shell: %s", url)
            return None, False, False, False, False

        low = body.lstrip()[:200].lower()
        looks_html = low.startswith("<!doctype") or low.startswith("<html")
        if looks_html or "text/html" in str(solution.get("headers") or "").lower():
            tip = body[:65536]
            if is_attachment_not_found(tip):
                return None, False, False, False, True
            if is_attachment_login_required(tip):
                return None, False, True, False, False
            if is_attachment_download_limited(tip):
                return None, True, False, True, False
            if is_attachment_denied(tip):
                return None, True, False, False, False
            # 普通 HTML 提示页，无附件体
            return None, False, False, False, False

        # Flare 以字符串返回；文本附件用 utf-8，其它字节尽力保留
        try:
            data = body.encode("utf-8")
        except UnicodeEncodeError:
            data = body.encode("latin-1", errors="replace")
        if _skip_oversized(url, len(data)):
            return None, False, False, False, False
        log.info(
            "FlareSolverr attach ok: %s (%s bytes)",
            url,
            len(data),
        )
        return data, False, False, False, False

    async def _fetch_bytes_via_page(
        self, url: str
    ) -> tuple[bytes | None, bool, bool, bool, bool]:
        """返回 (bytes, denied, login_required, daily_limited, empty_or_missing)。

        empty_or_missing：0 字节空壳 / HTTP 404 / Not Found 提示页。
        """

        async def _on_page(page: Any) -> tuple[bytes | None, bool, bool, bool, bool]:
            try:
                # Content-Length / 实际体积超限则不 btoa，避免 2～3× 峰值
                # AbortSignal：避免 fetch 挂起拖满整帖墙钟
                fetch_ms = max(5000, int(ATTACH_PAGE_OP_SEC * 1000) - 2000)
                result = await page.evaluate(
                    """
                    async ({ targetUrl, maxBytes, fetchMs }) => {
                        const ctrl = new AbortController();
                        const timer = setTimeout(() => ctrl.abort(), fetchMs);
                        let resp;
                        try {
                            resp = await fetch(targetUrl, {
                                credentials: 'include',
                                signal: ctrl.signal,
                            });
                        } finally {
                            clearTimeout(timer);
                        }
                        const contentType = resp.headers.get('content-type') || '';
                        const disposition = resp.headers.get('content-disposition') || '';
                        const cl = resp.headers.get('content-length');
                        if (cl) {
                            const n = parseInt(cl, 10);
                            if (!Number.isNaN(n) && n > maxBytes) {
                                return {
                                    status: resp.status,
                                    contentType,
                                    disposition,
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
                                disposition,
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
                            disposition,
                            body: btoa(binary),
                            size: bytes.length,
                        };
                    }
                    """,
                    {
                        "targetUrl": url,
                        "maxBytes": MAX_ATTACHMENT_BYTES,
                        "fetchMs": fetch_ms,
                    },
                )
            except Exception as exc:
                log.debug("Attachment page fetch failed %s: %s", url, exc)
                return None, False, False, False, False

            if not result:
                return None, False, False, False, False
            status = int(result.get("status") or 0)
            if status == 404:
                log.info("Attachment HTTP 404: %s", url)
                return None, False, False, False, True
            if status != 200:
                return None, False, False, False, False

            if result.get("skipped") == "too_large":
                log.info(
                    "Attachment skipped (too large): %s (%s bytes)",
                    url,
                    result.get("size"),
                )
                return None, False, False, False, False

            content_type = (result.get("contentType") or "").lower()
            disposition = (result.get("disposition") or "").lower()
            data = base64.b64decode(result.get("body") or "")
            if not data:
                # 200 + 下载头/二进制类型 + 0 字节 → 空文件（非网络失败）
                looks_attach = (
                    "attachment" in disposition
                    or "filename" in disposition
                    or "octet-stream" in content_type
                    or "bittorrent" in content_type
                )
                if looks_attach:
                    log.info("Attachment empty file (0 bytes): %s", url)
                    return None, False, False, False, True
                return None, False, False, False, False
            if _skip_oversized(url, len(data)):
                return None, False, False, False, False

            if "text/html" in content_type or data.startswith(b"<!DOCTYPE") or data.startswith(b"<html"):
                # 提示页导航很长，登录/日限文案常在 8KB+；勿只看前 4KB
                html = _decode_bytes(data[:65536])
                if is_attachment_not_found(html):
                    log.info("Attachment not found tip: %s", url)
                    return None, False, False, False, True
                if is_attachment_login_required(html):
                    log.info("Attachment login required: %s", url)
                    return None, False, True, False, False
                if is_attachment_download_limited(html):
                    log.info("Attachment daily limited: %s", url)
                    return None, True, False, True, False
                if is_attachment_denied(html):
                    log.info("Attachment denied: %s", url)
                    return None, True, False, False, False
                return None, False, False, False, False
            return data, False, False, False, False

        return await self.session.run_on_page(_on_page, timeout=ATTACH_PAGE_OP_SEC)

    async def _download_raw_via_ui(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        suffix: str,
    ) -> tuple[bytes | None, bool, bool, bool, bool]:
        """返回 (bytes, denied, login_required, daily_limited, empty_file)。"""

        async def _on_page(page: Any) -> tuple[bytes | None, bool, bool, bool, bool]:
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
                return None, False, False, False, False

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
                    if size == 0:
                        log.info(
                            "Attachment UI empty file (0 bytes): %s",
                            attachment.name,
                        )
                        return None, False, False, False, True
                    if _skip_oversized(attachment.name or attachment.url, size):
                        return None, False, False, False, False
                    data = temp_path.read_bytes()
                finally:
                    temp_path.unlink(missing_ok=True)
                if data:
                    return data, False, False, False, False
            except Exception:
                pass

            popup = None
            try:
                async with page.expect_popup(timeout=popup_ms) as popup_info:
                    await locator.click(timeout=5000)
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded", timeout=popup_ms)
                html = await popup.content()
                if is_attachment_not_found(html):
                    log.info("Attachment popup not found: %s", attachment.name)
                    return None, False, False, False, True
                if is_attachment_login_required(html):
                    log.info("Attachment popup login required: %s", attachment.name)
                    return None, False, True, False, False
                if is_attachment_download_limited(html):
                    log.info("Attachment popup daily limited: %s", attachment.name)
                    return None, True, False, True, False
                if is_attachment_denied(html):
                    log.info("Attachment popup denied: %s", attachment.name)
                    return None, True, False, False, False
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
                    return payload.encode("utf-8", errors="ignore"), False, False, False, False
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

            return None, False, False, False, False

        return await self.session.run_on_page(_on_page, timeout=ATTACH_PAGE_OP_SEC)

    async def _extract_attachment_text(
        self,
        attachment: DownloadAttachment,
        data: bytes,
        passwords: list[str] | None = None,
    ) -> str:
        """解压/解码放到线程池并限时，避免 rar/unrar 同步挂死事件循环。"""
        if not data:
            return ""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _text_from_attachment_bytes,
                    attachment,
                    data,
                    passwords,
                ),
                timeout=ATTACH_EXTRACT_SEC,
            )
        except asyncio.TimeoutError:
            log.warning(
                "Attachment extract timed out (%.0fs): %s",
                ATTACH_EXTRACT_SEC,
                attachment.name,
            )
            return ""
        except Exception as exc:
            log.warning(
                "Attachment extract failed %s: %s", attachment.name, exc
            )
            return ""

    async def _download_one(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        passwords: list[str] | None = None,
    ) -> tuple[str, bool, bool, bool, bool, bool, bool]:
        """返回 (text, denied, downloaded, login_required, daily_limited, empty_torrent, empty_attachment)。"""
        denied = False
        login_required = False
        daily_limited = False
        downloaded = False
        empty_torrent = False
        empty_attachment = False
        (
            data,
            fetch_denied,
            fetch_login,
            fetch_limited,
            fetch_empty,
        ) = await self._fetch_bytes_via_page(attachment.url)
        denied = denied or fetch_denied
        login_required = login_required or fetch_login
        daily_limited = daily_limited or fetch_limited
        if fetch_empty:
            empty_attachment = True
            if attachment.kind == "torrent":
                empty_torrent = True
        if data:
            downloaded = True
            text = await self._extract_attachment_text(
                attachment, data, passwords=passwords
            )
            if text.strip():
                return (
                    text,
                    denied,
                    downloaded,
                    login_required,
                    daily_limited,
                    False,
                    False,
                )

        # Playwright 页无 clearance 时，页面 fetch 常空：改走 FlareSolverr 同出口
        # 同帖若已试 Flare 无收获，后续附件跳过 Flare（多附件防串行卡死）
        if (
            not data
            and not self._skip_flare
            and not (fetch_denied or fetch_login or fetch_limited or fetch_empty)
        ):
            (
                flare_data,
                flare_denied,
                flare_login,
                flare_limited,
                flare_empty,
            ) = await asyncio.to_thread(self._fetch_bytes_via_flare, attachment.url)
            denied = denied or flare_denied
            login_required = login_required or flare_login
            daily_limited = daily_limited or flare_limited
            if flare_empty:
                empty_attachment = True
                if attachment.kind == "torrent":
                    empty_torrent = True
            if flare_data:
                downloaded = True
                text = await self._extract_attachment_text(
                    attachment, flare_data, passwords=passwords
                )
                if text.strip():
                    return (
                        text,
                        denied,
                        downloaded,
                        login_required,
                        daily_limited,
                        False,
                        False,
                    )
            data = flare_data
            if (
                not flare_data
                and not flare_denied
                and not flare_login
                and not flare_limited
                and not flare_empty
            ):
                self._skip_flare = True
                log.info(
                    "Flare attach miss for %s — skip Flare for rest of thread",
                    attachment.name,
                )

        # 页面/Flare 已明确无权/需登录/日限且无字节：UI 再点一次通常同样失败，省一轮
        if (denied or login_required or daily_limited) and not data:
            return (
                "",
                denied,
                downloaded,
                login_required,
                daily_limited,
                empty_torrent,
                empty_attachment,
            )

        # 空壳 / Not Found：fetch 已确认，UI 再点多半同样空，直接返回
        if empty_attachment and not data:
            return (
                "",
                denied,
                downloaded,
                login_required,
                daily_limited,
                empty_torrent,
                True,
            )

        suffix = _attachment_ui_suffix(attachment)
        (
            ui_data,
            ui_denied,
            ui_login,
            ui_limited,
            ui_empty,
        ) = await self._download_raw_via_ui(
            attachment, timeout, suffix=suffix
        )
        denied = denied or ui_denied
        login_required = login_required or ui_login
        daily_limited = daily_limited or ui_limited
        if ui_empty:
            empty_attachment = True
            if attachment.kind == "torrent":
                empty_torrent = True
        if ui_data:
            downloaded = True
            text = await self._extract_attachment_text(
                attachment, ui_data, passwords=passwords
            )
            if text.strip():
                return (
                    text,
                    denied,
                    downloaded,
                    login_required,
                    daily_limited,
                    False,
                    False,
                )

        return (
            "",
            denied,
            downloaded,
            login_required,
            daily_limited,
            empty_torrent,
            empty_attachment,
        )

    async def download_tail(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = MAX_ATTACHMENTS_PER_THREAD,
        timeout: float = 45,
        preferred_link: str | None = None,
        quota_stop: bool = True,
    ) -> AttachmentFetchResult:
        """正文无链 / 正文不合格复判：按优先序逐个轮询附件。

        硬规则：每下完一个有链附件即试算入库；
        - 不合格 → 必须继续下一个；
        - 单资源有标题 N配额（quota_stop=True）：**扫完所有可用附件**后再与额度对比
          （分卷/备用 txt 勿因中途「成功」早停）；配额已齐仍扫完其余可用附件。
        - 多资源（quota_stop=False）：不做额度匹配；试算合格且无剩余必要时可停。
        例外：
        - **任一附件无权/需登录 → 立即停并 denied**（丢弃已下部分文本，整帖占位）；
        - 附件日限（今天下载请明天再来）立刻停，入附件队列；
        - **整帖墙钟 / 单附件超时 / 连续空转早停**（防多附件串行卡死爬虫）；
        - 列表区已写明无权 → 不下附件直接 denied。
        """
        if not self.session._ready:
            return AttachmentFetchResult(failed=True)

        # 列表/楼主已明示无权：勿逐个下载空转
        if listing_shows_attach_denied(html):
            log.info("Attachment listing already shows denied — stub without download")
            return AttachmentFetchResult(denied=True)

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

        quota_expect = _quota_expect_from_html(html) if quota_stop else None
        chunks: list[str] = []
        any_downloaded = False
        any_daily_limited = False
        any_empty_torrent = False
        any_empty_attachment = False
        hit_wall = False
        hit_empty_streak = False
        streak_had_timeout = False
        empty_streak = 0
        deadline = time.monotonic() + float(ATTACH_POLL_WALL_SEC)

        def _bump_empty_streak(*, timed_out: bool = False) -> bool:
            """累加空转；达阈值返回 True 表示应停。"""
            nonlocal empty_streak, hit_empty_streak, streak_had_timeout
            empty_streak += 1
            if timed_out:
                streak_had_timeout = True
            if empty_streak >= ATTACH_EMPTY_STREAK_STOP:
                hit_empty_streak = True
                log.warning(
                    "Attachment empty/timeout streak %s — stop polling",
                    empty_streak,
                )
                return True
            return False

        for idx, attachment in enumerate(attachments):
            if is_directory_tree_attachment_name(attachment.name):
                log.info("Attachment skip directory-tree name: %s", attachment.name)
                continue
            remain_wall = deadline - time.monotonic()
            # 至少给第一个附件机会；其后剩余不足则停
            if idx > 0 and remain_wall <= 0:
                hit_wall = True
                log.warning(
                    "Attachment poll wall deadline (%.0fs) — stop after %s/%s",
                    ATTACH_POLL_WALL_SEC,
                    idx,
                    len(attachments),
                )
                break
            one_timeout = min(
                float(ATTACH_ONE_WALL_SEC),
                max(0.5, remain_wall if remain_wall > 0 else float(ATTACH_ONE_WALL_SEC)),
            )
            try:
                try:
                    (
                        text,
                        denied,
                        downloaded,
                        login_required,
                        daily_limited,
                        empty_torrent,
                        empty_attachment,
                    ) = await asyncio.wait_for(
                        self._download_one(
                            attachment, timeout, passwords=passwords
                        ),
                        timeout=one_timeout,
                    )
                except asyncio.TimeoutError:
                    log.warning(
                        "Attachment %s timed out (%.0fs) — streak %s/%s",
                        attachment.name,
                        one_timeout,
                        empty_streak + 1,
                        ATTACH_EMPTY_STREAK_STOP,
                    )
                    if _bump_empty_streak(timed_out=True):
                        break
                    continue
                if empty_torrent or empty_attachment:
                    any_empty_torrent = any_empty_torrent or empty_torrent
                    any_empty_attachment = True
                    log.info(
                        "Attachment %s empty/missing — streak %s/%s",
                        attachment.name,
                        empty_streak + 1,
                        ATTACH_EMPTY_STREAK_STOP,
                    )
                    if _bump_empty_streak():
                        break
                    continue
                if daily_limited:
                    any_daily_limited = True
                    log.info(
                        "Attachment %s daily limited — stop polling",
                        attachment.name,
                    )
                    break
                if login_required or denied:
                    # 多附件：任一无权/需登录立即占位，勿再试其它附件（避免部分链误判合格）
                    log.info(
                        "Attachment %s %s — stop all attaches (stub denied)",
                        attachment.name,
                        "login required" if login_required else "denied",
                    )
                    return AttachmentFetchResult(
                        text="",
                        downloaded=any_downloaded,
                        denied=True,
                        login_required=bool(login_required),
                    )
                if downloaded:
                    any_downloaded = True
                if not text.strip():
                    log.info(
                        "Attachment %s (%s) yielded no text — streak %s/%s",
                        attachment.name,
                        attachment.kind,
                        empty_streak + 1,
                        ATTACH_EMPTY_STREAK_STOP,
                    )
                    if _bump_empty_streak():
                        break
                    continue
                empty_streak = 0
                chunks.append(text)
                if not _text_has_importable_link(text):
                    log.info(
                        "Attachment %s (%s) → %s chars — continue polling",
                        attachment.name,
                        attachment.kind,
                        len(text),
                    )
                    continue

                merged = _pick_best_archive_texts(chunks)
                have = _count_importable_links(merged)
                try:
                    from parsers.resource_frame import count_post_quota_links

                    provided = count_post_quota_links(merged)
                except Exception:
                    provided = have
                rest = attachments[idx + 1 :]
                if not rest:
                    log.info(
                        "Attachment %s (%s) → %s links (provided %s) — last attach, stop",
                        attachment.name,
                        attachment.kind,
                        have,
                        provided,
                    )
                    break

                # 硬规则：不合格必须继续；单资源配额未齐也继续（即使 cloud_soft 写成「成功」）
                # 额度对照「提供链数」非去重入库数（同 hash 重复张贴仍计）
                still_unqual = _attach_merge_still_unqualified(
                    html,
                    merged,
                    preferred_link=preferred_link,
                    base_url=base_url,
                )
                short_quota = (
                    bool(quota_stop)
                    and bool(quota_expect)
                    and provided < int(quota_expect)
                )
                # 有标题额度：必须扫完所有可用附件再与额度对比（分卷/备用 txt 勿早停）
                exhaust_for_quota = bool(quota_stop) and bool(quota_expect) and bool(rest)
                if still_unqual or short_quota or exhaust_for_quota:
                    if exhaust_for_quota and not still_unqual and not short_quota:
                        why = f"额度对照需扫完附件 (已提供{provided}/配额{quota_expect})"
                    elif still_unqual:
                        why = "不合格"
                    else:
                        why = f"提供链数{provided}<配额{quota_expect}"
                    log.info(
                        "Attachment %s (%s) → %s — continue next (%s left)",
                        attachment.name,
                        attachment.kind,
                        why,
                        len(rest),
                    )
                    continue

                log.info(
                    "Attachment %s (%s) → 合格 (%s links) — stop polling",
                    attachment.name,
                    attachment.kind,
                    have,
                )
                break
            except Exception as exc:
                log.warning("Attachment download failed %s: %s", attachment.name, exc)

        result_text = _pick_best_archive_texts(chunks)
        # 日限：优先标 daily_limited，供上层入附件队列
        if any_daily_limited:
            return AttachmentFetchResult(
                text="",
                downloaded=any_downloaded or bool(result_text),
                denied=True,
                login_required=False,
                daily_limited=True,
            )
        if result_text and _text_has_importable_link(result_text):
            return AttachmentFetchResult(
                text=result_text, downloaded=True, denied=False, login_required=False
            )
        # 墙钟耗尽 / 超时连击仍无可用链 → 失败待重试
        if (hit_wall or (hit_empty_streak and streak_had_timeout)) and not (
            result_text and _text_has_importable_link(result_text)
        ):
            return AttachmentFetchResult(
                text=result_text or "",
                downloaded=any_downloaded or bool(result_text),
                failed=True,
            )
        if result_text:
            return AttachmentFetchResult(text=result_text, downloaded=True)
        if any_downloaded:
            return AttachmentFetchResult(downloaded=True)
        # 空壳 / Not Found（含连续空附件早停）：跳过，勿「附件下载失败」重试
        if any_empty_attachment or any_empty_torrent:
            return AttachmentFetchResult(
                empty_attachment=True,
                empty_torrent=any_empty_torrent,
            )
        if hit_empty_streak:
            return AttachmentFetchResult(failed=True)
        return AttachmentFetchResult(failed=True)

    async def download_torrents(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = MAX_ATTACHMENTS_PER_THREAD,
        timeout: float = 45,
        preferred_link: str | None = None,
        quota_stop: bool = True,
    ) -> AttachmentFetchResult:
        """与 download_tail 相同：全类型附件按板块频次逐个轮询。"""
        return await self.download_tail(
            html,
            base_url,
            max_files=max_files,
            timeout=timeout,
            preferred_link=preferred_link or "magnet",
            quota_stop=quota_stop,
        )


async def fetch_attachments_for_outcome(
    session: SessionManager,
    *,
    html: str,
    thread_url: str,
    attachment_kind: str,
    timeout: float = 45,
    preferred_link: str | None = None,
    quota_stop: bool = True,
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

    http_ok = bool(
        html
        and len(html) > 8000
        and looks_like_attachment_zone(html)
        and not _html_is_cf_challenge(html)
    )
    page_cf = bool(page_html) and _html_is_cf_challenge(page_html)
    page_ok = bool(
        page_html
        and len(page_html) > 1000
        and looks_like_attachment_zone(page_html)
        and not page_cf
    )
    if page_ok:
        if html and html is not page_html:
            log.info(
                "attachments: use browser HTML for listing (http_zone=%s page_len=%s)",
                http_ok,
                len(page_html),
            )
        html = page_html
    elif page_cf and http_ok:
        # 浏览器卡在 CF，但读帖 HTML（Flare）已有附件区 → 用读帖列表 + Flare 下附件
        log.warning(
            "attachments: browser page is Cloudflare — keep HTTP/Flare HTML for listing"
        )
    elif (not http_ok) and page_html and len(page_html) > 1000 and not page_cf:
        html = page_html

    # attachment_kind 仅作缺省主链提示；显式 preferred_link 优先
    link_pref = preferred_link
    if not link_pref:
        link_pref = "magnet" if attachment_kind == "torrent" else "ed2k"

    if attachment_kind == "torrent":
        return await downloader.download_torrents(
            html,
            thread_url,
            timeout=timeout,
            preferred_link=link_pref,
            quota_stop=quota_stop,
        )
    if attachment_kind == "txt_tail":
        return await downloader.download_tail(
            html,
            thread_url,
            timeout=timeout,
            preferred_link=link_pref,
            quota_stop=quota_stop,
        )
    return AttachmentFetchResult(failed=True)
