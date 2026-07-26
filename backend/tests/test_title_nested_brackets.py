"""片名含装饰性【标签】时不得截成前缀（如 ❤️√）。"""

from __future__ import annotations

from parsers.content import (
    _clip_field_value,
    build_structured_description,
    extract_metadata,
    normalize_metadata_for_board,
)
from parsers.links import parse_thread_dual


_FILM = "❤️√ 【午夜寻花】酒店约高颜值兼职美女 完美身材有容乃大 大长腿翘臀 无毛嫩穴 草的嗷嗷叫"


def test_clip_title_keeps_decorative_brackets():
    assert _clip_field_value(_FILM, label="影片名称") == _FILM.replace("\ufe0f", "")
    # 繁体键同样按片名裁
    assert "午夜寻花" in _clip_field_value(_FILM, label="影片名稱")
    # 非片名字段仍可在任意【】处截
    assert _clip_field_value(_FILM, label="影片说明") == "❤√"


def test_extract_and_desc_board_142_keeps_full_film_name():
    text = (
        f"【影片名称】：{_FILM}\n"
        "【影片格式】：MP4\n"
        "【影片大小】：1640MB\n"
        "【影片说明】：无码\n"
    )
    meta = extract_metadata(text)
    assert "午夜寻花" in (meta.get("影片名称") or "")
    assert not (meta.get("影片名称") or "").endswith("❤√")
    assert (meta.get("影片名称") or "").rstrip("❤√ ").find("午夜") >= 0

    norm = normalize_metadata_for_board(meta, board_fid="142:697")
    name = norm.get("资源名称") or norm.get("影片名称") or ""
    assert "午夜寻花" in name
    assert "草的嗷嗷叫" in name
    # 转帖区常见【影片说明】：无码 → 是否有码
    assert norm.get("是否有码") == "无码"

    desc = build_structured_description(norm, board_fid="142:697")
    assert "午夜寻花" in desc
    assert "【是否有码】：无码" in desc
    assert "【资源名称】：❤√\n" not in desc  # 不得只剩前缀


def test_parse_thread_dual_filename_not_truncated():
    html = f"""
    <html><head><title>【BT/磁力】【午夜寻花】酒店约高颜值兼职美女 完美身材有容乃大 大长腿翘臀 无毛嫩穴 草的嗷嗷叫 - 转帖交流区</title></head>
    <body>
      <span id="thread_subject">【BT/磁力】【午夜寻花】酒店约高颜值兼职美女 完美身材有容乃大 大长腿翘臀 无毛嫩穴 草的嗷嗷叫</span>
      <div id="postmessage_1">
        【影片名称】：{_FILM}<br>
        【影片格式】：MP4<br>
        【影片大小】：1640MB<br>
        【影片说明】：无码<br>
        magnet:?xt=urn:btih:AD2D99AF51EC130B81038CC02B54CF54C956F354&amp;dn=demo
      </div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    dual = parse_thread_dual(html, tid=3332677, preferred_link="magnet", board_fid="142:697")
    assert dual.assets
    fn = dual.assets[0].filename or ""
    assert "午夜寻花" in fn
    assert "草的嗷嗷叫" in fn
    assert fn.strip() != "❤√"
    assert "午夜寻花" in (dual.description or "")
