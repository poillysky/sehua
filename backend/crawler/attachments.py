"""下载并解析帖内附件：txt / zip·rar 内 txt · torrent→magnet。"""

from __future__ import annotations

import base64
import io
import logging
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
    extract_download_attachments,
    filter_tail_attachments,
    filter_torrent_attachments,
    is_attachment_denied,
)
from parsers.thread_gates import has_115_sha_link
from parsers.torrent import parse_torrent_bytes

log = logging.getLogger(__name__)


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="ignore")


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


def _archive_password_candidates(html: str) -> list[str]:
    """从一楼正文抽解压密码，并生成常见变体（空格/@）。"""
    from parsers.content import extract_password, parse_thread_content

    content = parse_thread_content(html or "")
    raw = (content.extract_password or "").strip()
    if not raw:
        # 标签拆开后「密码」与 www.98T.la@ 仍可能被漏抽，再扫一遍纯文本
        blob = f"{content.plain_text or ''}\n{content.blockcode_text or ''}"
        raw = (extract_password(blob) or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
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
    for cand in variants:
        c = (cand or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _txt_names_in_archive(names: list[str]) -> list[str]:
    return [n for n in names if n and not n.endswith("/") and n.lower().endswith(".txt")]


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
    """用 7z 解出压缩包内首个非空 .txt；内层 zip/rar 用同一组密码再解。"""
    if depth > 24:
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
            for path in sorted(out_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() == ".txt":
                    try:
                        text = _decode_bytes(path.read_bytes())
                    except OSError:
                        continue
                    if text.strip():
                        return text
            # 外层解开后若只有内层压缩包，继续用帖内密码解
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
                    nested = path.read_bytes()
                except OSError:
                    continue
                if len(nested) < 32:
                    continue
                text = _extract_txt_from_archive(
                    nested, kind, passwords=pwds, depth=depth + 1
                )
                if text.strip():
                    return text
    return ""


def _extract_zip_pyzipper(
    data: bytes, passwords: list[str] | None = None, *, depth: int = 0
) -> str:
    """AES zip（stdlib 不解）优先走 pyzipper；支持内层 zip/rar。"""
    if depth > 24:
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
                for name in _txt_names_in_archive(names):
                    text = _decode_bytes(archive.read(name))
                    if text.strip():
                        return text
                for name, kind in _nested_archive_members(names):
                    try:
                        nested = archive.read(name)
                    except Exception:
                        continue
                    text = _extract_txt_from_archive(
                        nested, kind, passwords=pwds, depth=depth + 1
                    )
                    if text.strip():
                        return text
        except Exception:
            continue
    return ""


def _extract_rar_text(
    data: bytes, passwords: list[str] | None = None, *, depth: int = 0
) -> str:
    if depth > 24:
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
                            for name in _txt_names_in_archive(names):
                                text = _decode_bytes(archive.read(name))
                                if text.strip():
                                    return text
                            for name, kind in _nested_archive_members(names):
                                try:
                                    nested = archive.read(name)
                                except Exception:
                                    continue
                                text = _extract_txt_from_archive(
                                    nested, kind, passwords=pwds, depth=depth + 1
                                )
                                if text.strip():
                                    return text
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
    if depth > 24:
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
        for name in _txt_names_in_archive(names):
            for pwd in pwd_attempts:
                try:
                    raw = archive.read(name, pwd=pwd) if pwd else archive.read(name)
                except Exception:
                    continue
                text = _decode_bytes(raw)
                if text.strip():
                    return text
        for name, kind in _nested_archive_members(names):
            for pwd in pwd_attempts:
                try:
                    nested = archive.read(name, pwd=pwd) if pwd else archive.read(name)
                except Exception:
                    continue
                text = _extract_txt_from_archive(
                    nested, kind, passwords=pwds, depth=depth + 1
                )
                if text.strip():
                    return text
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
    if kind == "zip":
        return _extract_zip_txt(data, passwords=passwords, depth=depth)
    if kind == "rar":
        return _extract_rar_text(data, passwords=passwords, depth=depth)
    return ""


def _text_from_attachment_bytes(
    attachment: DownloadAttachment,
    data: bytes,
    passwords: list[str] | None = None,
) -> str:
    if attachment.kind == "torrent":
        magnet = parse_torrent_bytes(data, filename_hint=attachment.name)
        return magnet.link if magnet else ""
    if attachment.kind in ("zip", "rar"):
        return _extract_txt_from_archive(data, attachment.kind, passwords=passwords)
    text = _decode_bytes(data)
    if "<html" in text.lower()[:200]:
        return ""
    return text


def _attachment_ui_suffix(attachment: DownloadAttachment) -> str:
    if attachment.kind == "torrent":
        return ".torrent"
    if attachment.kind in ("zip", "rar"):
        return f".{attachment.kind}"
    return ".txt"


class AttachmentDownloader:
    """基于已进站 SessionManager（Playwright 页）下载附件。"""

    def __init__(self, session: SessionManager):
        self.session = session

    async def ensure_thread_page(self, thread_url: str, *, timeout_ms: int = 60000) -> str:
        html = await self.session.fetch_html(thread_url, timeout_ms=timeout_ms)
        return html

    async def _fetch_bytes_via_page(self, url: str) -> tuple[bytes | None, bool]:
        async def _on_page(page: Any) -> tuple[bytes | None, bool]:
            try:
                result = await page.evaluate(
                    """
                    async (targetUrl) => {
                        const resp = await fetch(targetUrl, { credentials: 'include' });
                        const contentType = resp.headers.get('content-type') || '';
                        const buf = await resp.arrayBuffer();
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
                        };
                    }
                    """,
                    url,
                )
            except Exception as exc:
                log.debug("Attachment page fetch failed %s: %s", url, exc)
                return None, False

            if not result or result.get("status") != 200:
                return None, False

            content_type = (result.get("contentType") or "").lower()
            data = base64.b64decode(result.get("body") or "")
            if not data:
                return None, False

            if "text/html" in content_type or data.startswith(b"<!DOCTYPE") or data.startswith(b"<html"):
                html = _decode_bytes(data[:4000])
                if is_attachment_denied(html):
                    log.info("Attachment denied: %s", url)
                    return None, True
                return None, False
            return data, False

        return await self.session.run_on_page(_on_page)

    async def _download_raw_via_ui(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        suffix: str,
    ) -> tuple[bytes | None, bool]:
        async def _on_page(page: Any) -> tuple[bytes | None, bool]:
            locator = page.locator("a", has_text=attachment.name).first
            if await locator.count() == 0:
                aid = ""
                if "aid=" in attachment.url:
                    aid = attachment.url.split("aid=")[-1][:16]
                if aid:
                    locator = page.locator(f"a[href*='attachment'][href*='{aid}']").first
            if await locator.count() == 0:
                return None, False

            try:
                async with page.expect_download(timeout=min(timeout, 12) * 1000) as download_info:
                    await locator.click(timeout=4000)
                download = await download_info.value
                temp_path = Path(tempfile.gettempdir()) / f"sht-attach-{int(time.time() * 1000)}{suffix}"
                await download.save_as(temp_path)
                data = temp_path.read_bytes()
                temp_path.unlink(missing_ok=True)
                if data:
                    return data, False
            except Exception:
                pass

            try:
                async with page.expect_popup(timeout=min(timeout, 10) * 1000) as popup_info:
                    await locator.click(timeout=4000)
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded", timeout=min(timeout, 15) * 1000)
                html = await popup.content()
                if is_attachment_denied(html):
                    log.info("Attachment popup denied: %s", attachment.name)
                    await popup.close()
                    return None, True
                text = _decode_bytes(html.encode("utf-8", errors="ignore"))
                await popup.close()
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
                    return payload.encode("utf-8", errors="ignore"), False
            except Exception as exc:
                log.debug("Attachment popup failed %s: %s", attachment.name, exc)

            return None, False

        return await self.session.run_on_page(_on_page)

    async def _download_one(
        self,
        attachment: DownloadAttachment,
        timeout: float,
        *,
        passwords: list[str] | None = None,
    ) -> tuple[str, bool, bool]:
        denied = False
        downloaded = False
        data, fetch_denied = await self._fetch_bytes_via_page(attachment.url)
        denied = denied or fetch_denied
        if data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, data, passwords=passwords)
            if text.strip():
                return text, denied, downloaded

        suffix = _attachment_ui_suffix(attachment)
        ui_data, ui_denied = await self._download_raw_via_ui(
            attachment, timeout, suffix=suffix
        )
        denied = denied or ui_denied
        if ui_data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, ui_data, passwords=passwords)
            if text.strip():
                return text, denied, downloaded

        return "", denied, downloaded

    async def download_tail(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = 3,
        timeout: float = 45,
    ) -> AttachmentFetchResult:
        """电驴板：正文无链时下尾部 txt/zip/rar 并抽出文本。"""
        if not self.session._ready:
            return AttachmentFetchResult(failed=True)

        attachments = filter_tail_attachments(
            extract_download_attachments(base_url, html),
            limit=max_files,
        )
        if not attachments:
            return AttachmentFetchResult()

        passwords = _archive_password_candidates(html)
        if passwords:
            log.info("Archive extract passwords from post: %s", passwords[0])

        chunks: list[str] = []
        any_denied = False
        any_downloaded = False
        for attachment in attachments:
            try:
                text, denied, downloaded = await self._download_one(
                    attachment, timeout, passwords=passwords
                )
                if denied:
                    any_denied = True
                if downloaded:
                    any_downloaded = True
                if not text.strip():
                    continue
                chunks.append(text)
                log.info(
                    "Downloaded %s attachment %s (%s chars)",
                    attachment.kind,
                    attachment.name,
                    len(text),
                )
                # 附件一旦识别 115sha，立即停止继续下其余附件
                if has_115_sha_link(text):
                    log.info(
                        "115sha in attachment %s — stop further attachment downloads",
                        attachment.name,
                    )
                    break
            except Exception as exc:
                log.warning("Attachment download failed %s: %s", attachment.name, exc)

        result_text = "\n\n".join(chunks)
        if result_text:
            # 保留 denied：若语料仍解析不出链，上层可占位入库
            return AttachmentFetchResult(
                text=result_text, downloaded=True, denied=any_denied
            )
        if any_denied:
            # 任一附件明确无权限，且没有可用链接文本 → 占位；勿被「空附件 downloaded」掩盖
            return AttachmentFetchResult(downloaded=any_downloaded, denied=True)
        if any_downloaded:
            return AttachmentFetchResult(downloaded=True)
        return AttachmentFetchResult(failed=True)
    async def download_torrents(
        self,
        html: str,
        base_url: str,
        *,
        max_files: int = 3,
        timeout: float = 45,
    ) -> AttachmentFetchResult:
        """磁力板：正文无 magnet 时下 .torrent → magnet URI。"""
        if not self.session._ready:
            return AttachmentFetchResult(failed=True)

        attachments = filter_torrent_attachments(
            extract_download_attachments(base_url, html),
            limit=max_files,
        )
        if not attachments:
            return AttachmentFetchResult()

        chunks: list[str] = []
        any_denied = False
        any_downloaded = False
        for attachment in attachments:
            try:
                magnet_uri, denied, downloaded = await self._download_one(attachment, timeout)
                if denied:
                    any_denied = True
                if downloaded:
                    any_downloaded = True
                if not magnet_uri.strip() or not magnet_uri.lower().startswith("magnet:"):
                    continue
                chunks.append(magnet_uri.strip())
                log.info(
                    "Torrent %s → magnet %s",
                    attachment.name,
                    magnet_uri[:80],
                )
            except Exception as exc:
                log.warning("Torrent attachment failed %s: %s", attachment.name, exc)

        result_text = "\n".join(chunks)
        if result_text:
            return AttachmentFetchResult(
                text=result_text, downloaded=True, denied=any_denied
            )
        if any_denied:
            return AttachmentFetchResult(downloaded=any_downloaded, denied=True)
        if any_downloaded:
            return AttachmentFetchResult(downloaded=True)
        return AttachmentFetchResult(failed=True)


async def fetch_attachments_for_outcome(
    session: SessionManager,
    *,
    html: str,
    thread_url: str,
    attachment_kind: str,
    timeout: float = 45,
) -> AttachmentFetchResult:
    """按判定 kind 下载：txt_tail | torrent。"""
    downloader = AttachmentDownloader(session)
    try:
        page_html = await downloader.ensure_thread_page(thread_url)
        if page_html and len(page_html) > 1000:
            html = page_html
    except Exception as exc:
        log.warning("Navigate to thread for attachments failed: %s", exc)

    if attachment_kind == "torrent":
        return await downloader.download_torrents(html, thread_url, timeout=timeout)
    if attachment_kind == "txt_tail":
        return await downloader.download_tail(html, thread_url, timeout=timeout)
    return AttachmentFetchResult(failed=True)
