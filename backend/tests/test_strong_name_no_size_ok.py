"""子名已识别但未写大小 → 不当漏资源名硬旁证（tid=27010485 类）。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def _asset(
    h: str,
    name: str,
    *,
    desc: str,
    size: int = 10 * 1024**3,
    prev: str = "http://a.jpg",
) -> ParsedAsset:
    return ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename=name,
        size=size,
        uri=f"magnet:?xt=urn:btih:{h}",
        description=desc,
        preview_images=[prev],
    )


def _parsed(title: str, assets: list[ParsedAsset]) -> DualParseResult:
    return DualParseResult(
        tid=1,
        title=title,
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
        layout="",
        had_attachments=False,
    )


def test_strong_name_without_size_not_incomplete_evidence():
    """14/15 有大小，1 条仅有片名+说明、无大小 → 不硬判资源名不合格。"""
    assets = []
    groups = []
    for i in range(14):
        h = f"{i:040X}"
        name = f"正常资源片名{i:02d}足够长可区分"
        a = _asset(
            h,
            name,
            desc=f"【影片名称】：{name}\n【影片大小】：1.2GB\n【影片格式】：MP4",
            prev=f"http://a{i}.jpg",
        )
        groups.append((name, a, [a]))
        assets.append(a)
    bad_name = "糖心露脸女神【多乙】糖心企划绝美女网红榜一大哥"
    bad = _asset(
        "F" * 40,
        bad_name,
        desc=f"【影片名称】：{bad_name}\n【影片说明】：无码",
        size=635_437_056,
        prev="http://bad.jpg",
    )
    groups.append((bad_name, bad, [bad]))
    assets.append(bad)
    frame = build_resource_frame(
        _parsed("★●最新の國產無碼合集", assets),
        named_groups=groups,
    )
    assert frame.verdict.status == "ok", frame.verdict.hard_errors
    assert not any("未写出大小" in e and "漏资源名旁证" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：正文含目标链接", frame).startswith("成功")
