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


def _extract_rar_text(data: bytes) -> str:
    try:
        import rarfile
    except ImportError:
        log.debug("rarfile not installed, skip rar attachment")
        return ""

    for tool in _rar_tool_candidates():
        rarfile.UNRAR_TOOL = tool
        try:
            with rarfile.RarFile(io.BytesIO(data)) as archive:
                for name in archive.namelist():
                    if name.endswith("/") or not name.lower().endswith(".txt"):
                        continue
                    text = _decode_bytes(archive.read(name))
                    if text.strip():
                        return text
        except Exception:
            continue

    seven = shutil.which("7z") or shutil.which("7z.exe")
    if not seven:
        log.info("RAR downloaded but no unrar/7z tool available")
        return ""

    with tempfile.TemporaryDirectory() as tmp:
        rar_path = Path(tmp) / "attach.rar"
        rar_path.write_bytes(data)
        try:
            proc = subprocess.run(
                [seven, "e", "-so", "-y", str(rar_path)],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("7z rar extract failed: %s", exc)
            return ""
        if proc.returncode == 0 and proc.stdout:
            text = _decode_bytes(proc.stdout)
            if text.strip():
                return text
    return ""


def _extract_txt_from_archive(data: bytes, kind: str) -> str:
    if kind == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for name in archive.namelist():
                    if name.endswith("/") or not name.lower().endswith(".txt"):
                        continue
                    text = _decode_bytes(archive.read(name))
                    if text.strip():
                        return text
        except zipfile.BadZipFile:
            log.info("Attachment is not a valid zip archive")
        return ""
    if kind == "rar":
        return _extract_rar_text(data)
    return ""


def _text_from_attachment_bytes(attachment: DownloadAttachment, data: bytes) -> str:
    if attachment.kind == "torrent":
        magnet = parse_torrent_bytes(data, filename_hint=attachment.name)
        return magnet.link if magnet else ""
    if attachment.kind in ("zip", "rar"):
        return _extract_txt_from_archive(data, attachment.kind)
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
        self, attachment: DownloadAttachment, timeout: float
    ) -> tuple[str, bool, bool]:
        denied = False
        downloaded = False
        data, fetch_denied = await self._fetch_bytes_via_page(attachment.url)
        denied = denied or fetch_denied
        if data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, data)
            if text.strip():
                return text, denied, downloaded

        suffix = _attachment_ui_suffix(attachment)
        ui_data, ui_denied = await self._download_raw_via_ui(
            attachment, timeout, suffix=suffix
        )
        denied = denied or ui_denied
        if ui_data:
            downloaded = True
            text = _text_from_attachment_bytes(attachment, ui_data)
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

        chunks: list[str] = []
        any_denied = False
        any_downloaded = False
        for attachment in attachments:
            try:
                text, denied, downloaded = await self._download_one(attachment, timeout)
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
