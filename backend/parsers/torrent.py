"""Parse .torrent files and build magnet URIs."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

from parsers.magnet import MagnetLink


def _bencode_value_end(data: bytes, start: int) -> int:
    if start >= len(data):
        raise ValueError("bencode out of range")

    tag = data[start : start + 1]
    if tag == b"i":
        end = data.index(b"e", start + 1)
        return end + 1
    if tag == b"l":
        index = start + 1
        while data[index : index + 1] != b"e":
            index = _bencode_value_end(data, index)
        return index + 1
    if tag == b"d":
        index = start + 1
        while data[index : index + 1] != b"e":
            index = _bencode_value_end(data, index)
            index = _bencode_value_end(data, index)
        return index + 1
    if tag in b"0123456789":
        colon = data.index(b":", start)
        length = int(data[start:colon])
        return colon + 1 + length
    raise ValueError(f"invalid bencode tag at {start}")


def _decode_at(data: bytes, start: int) -> tuple[Any, int]:
    tag = data[start : start + 1]
    if tag == b"i":
        end = data.index(b"e", start + 1)
        return int(data[start + 1 : end]), end + 1
    if tag == b"l":
        items: list[Any] = []
        index = start + 1
        while data[index : index + 1] != b"e":
            value, index = _decode_at(data, index)
            items.append(value)
        return items, index + 1
    if tag == b"d":
        mapping: dict[bytes, Any] = {}
        index = start + 1
        while data[index : index + 1] != b"e":
            key, index = _decode_at(data, index)
            value, index = _decode_at(data, index)
            if isinstance(key, bytes):
                mapping[key] = value
        return mapping, index + 1
    if tag in b"0123456789":
        colon = data.index(b":", start)
        length = int(data[start:colon])
        begin = colon + 1
        return data[begin : begin + length], begin + length
    raise ValueError(f"invalid bencode tag at {start}")


def extract_info_bencoded(torrent: bytes) -> bytes | None:
    """Return raw bencoded info dict bytes (for SHA1 infohash)."""
    marker = b"4:info"
    pos = 0
    while pos < len(torrent):
        idx = torrent.find(marker, pos)
        if idx < 0:
            return None
        value_start = idx + len(marker)
        if value_start < len(torrent) and torrent[value_start : value_start + 1] == b"d":
            end = _bencode_value_end(torrent, value_start)
            return torrent[value_start:end]
        pos = idx + 1
    return None


def _info_name(info: dict[bytes, Any]) -> str:
    raw = info.get(b"name", b"")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="ignore").strip()
    return ""


def _info_total_size(info: dict[bytes, Any]) -> int:
    if b"length" in info:
        try:
            return int(info[b"length"])
        except (TypeError, ValueError):
            return 0
    files = info.get(b"files")
    if not isinstance(files, list):
        return 0
    total = 0
    for item in files:
        if isinstance(item, dict) and b"length" in item:
            try:
                total += int(item[b"length"])
            except (TypeError, ValueError):
                continue
    return total


def build_magnet_uri(infohash: str, *, name: str = "", size: int = 0) -> str:
    uri = f"magnet:?xt=urn:btih:{infohash.upper()}"
    if name:
        uri += f"&dn={quote(name)}"
    if size > 0:
        uri += f"&xl={size}"
    return uri


def parse_torrent_bytes(data: bytes, *, filename_hint: str = "") -> MagnetLink | None:
    if not data:
        return None

    info_raw = extract_info_bencoded(data)
    if not info_raw:
        return None

    try:
        root, _ = _decode_at(data, 0)
    except ValueError:
        return None

    if not isinstance(root, dict):
        return None
    info = root.get(b"info")
    if not isinstance(info, dict):
        return None

    infohash = hashlib.sha1(info_raw).hexdigest().upper()
    if not infohash:
        return None

    name = _info_name(info) or filename_hint.replace(".torrent", "").strip()
    size = _info_total_size(info)
    link = build_magnet_uri(infohash, name=name, size=size)
    if not name:
        name = f"magnet-{infohash[:8]}"
    return MagnetLink(infohash=infohash, filename=name, size=size, link=link)


def parse_torrent_text(text: str) -> list[MagnetLink]:
    """Parse magnet lines produced from torrent attachments."""
    from parsers.magnet import parse_magnet_text

    return parse_magnet_text(text)
