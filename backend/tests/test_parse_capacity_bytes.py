"""正文/标题容量文案 → 字节（13V 66.7GB 等）。"""

from __future__ import annotations

from parsers.magnet import parse_capacity_bytes, _context_name_and_size


def test_plain_gb():
    assert parse_capacity_bytes("66.7GB") == int(66.7 * 1024**3)


def test_volumes_then_gb():
    assert parse_capacity_bytes("13V 66.7GB") == int(66.7 * 1024**3)


def test_volumes_slash_tb():
    assert parse_capacity_bytes("635V/1.3TB") == int(1.3 * 1024**4)
    assert parse_capacity_bytes("989V/1.5T") == int(1.5 * 1024**4)


def test_gb_then_volumes():
    assert parse_capacity_bytes("2.6G/1V/1配额") == int(2.6 * 1024**3)
    assert parse_capacity_bytes("3V/542M") == 542 * 1024**2


def test_from_resource_size_field():
    text = "【资源名称】：合集\n【资源大小】：13V 66.7GB\n【是否有码】：有码"
    assert parse_capacity_bytes(text) == int(66.7 * 1024**3)


def test_from_title_brackets():
    title = "【磁力分享】流川莉央更新至FOCS-095【13V 66.7GB】"
    assert parse_capacity_bytes(title) == int(66.7 * 1024**3)


def test_auntjudys_tb():
    assert (
        parse_capacity_bytes("【资源大小】：2820V 1.11TB") == int(1.11 * 1024**4)
    )


def test_context_prefers_size_field_with_volumes():
    blob = "【资源名称】：包\n【资源大小】：13V 66.7GB\nmagnet:?xt=urn:btih:" + ("A" * 40)
    pos = blob.index("magnet:")
    _name, size = _context_name_and_size(blob, pos, pos + 20)
    assert size == int(66.7 * 1024**3)
