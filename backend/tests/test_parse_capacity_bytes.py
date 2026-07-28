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


def test_resolution_4k_not_kilobytes():
    """片名里的 4K/8K 分辨率不是 4KB 容量。"""
    assert parse_capacity_bytes("蓝光4K&1080p") == 0
    assert parse_capacity_bytes("4K") == 0
    assert parse_capacity_bytes("8K HDR") == 0
    # 仍认真正的 KB
    assert parse_capacity_bytes("512KB") == 512 * 1024
    title = "【自转】【ed2k】蓝光4K&1080p英语发音【4V/214G/4配额】"
    assert parse_capacity_bytes(title) == int(214 * 1024**3)


def test_bare_number_in_film_size_assumes_gb():
    """【影片大小】：1.59 / [MP4/1.59] 漏单位 → 按 GB（tid=26937663）。"""
    assert parse_capacity_bytes("【影片大小】：1.59") == int(1.59 * 1024**3)
    assert parse_capacity_bytes("[MP4/1.59] 露脸清纯") == int(1.59 * 1024**3)
    assert parse_capacity_bytes("[MP4/1.59G]") == int(1.59 * 1024**3)
    # 过大裸数不瞎猜
    assert parse_capacity_bytes("【影片大小】：159") == 0

