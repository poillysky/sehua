"""【影片大小】不得吞掉【特 徵 碼 】等尾字段（tid 26694474）。"""

from parsers.content import _assemble_subresource_block, _block_field
from parsers.links import parse_thread_dual
from parsers.resource_names import SIZE_FIELD_FORMS


def test_block_field_size_stops_at_spaced_feature_code():
    chunk = (
        "【影片名称】：[MP4/4.39G]ABW-112\n"
        "【影片格式】：MP4\n"
        "【影片大小】：4.39G  \n"
        "【特 徵 碼 】：b625d381a482923f10b472bc8708069ce31b2030\n"
        "【清晰程度】：高清\n"
        "【做種期限】：5种或健康度1000\n"
    )
    assert _block_field(chunk, *SIZE_FIELD_FORMS) == "4.39G"


def test_block_field_size_stops_at_yanzheng_typo_hash_label():
    """老含及【验証码】（証）粘在大小同行（tid 26695669 类历史脏描述）。"""
    from parsers.content import _clip_field_value

    chunk = (
        "【影片名称】：91PCM001 清纯系JK女学生\n"
        "【影片大小】：0.52GB 【验証码】：AC7446B87C45497994294560A7445C80AEAB0DF6\n"
        "【影片说明】：无码\n"
    )
    assert _block_field(chunk, *SIZE_FIELD_FORMS) == "0.52GB"
    assert (
        _clip_field_value(
            "0.52GB 【验証码】：AC7446B87C45497994294560A7445C80AEAB0DF6",
            label="影片大小",
        )
        == "0.52GB"
    )

    scope = chunk + "magnet:?xt=urn:btih:AC7446B87C45497994294560A7445C80AEAB0DF6\n"
    block = _assemble_subresource_block(
        paired="AC7446B87C45497994294560A7445C80AEAB0DF6",
        name="91PCM001 清纯系JK女学生",
        scope=scope,
        field_lo=0,
        field_hi=len(scope),
        kind="film",
        lim=5,
        base_url="https://bbs.xfca2022.com/",
    )
    size_line = [ln for ln in block.description.splitlines() if ln.startswith("【影片大小】")][0]
    assert size_line == "【影片大小】：0.52GB"
    assert "验証" not in size_line
    assert block.size == int(0.52 * 1024**3)


def test_assemble_size_label_clean_with_spaced_feature_code():
    scope = (
        "【影片名称】：[MP4/4.39G]ABW-112破壊版\n"
        "【影片格式】：MP4\n"
        "【影片大小】：4.39G&nbsp;&nbsp;\n"
        "【特 徵 碼 】：b625d381a482923f10b472bc8708069ce31b2030\n"
        "【清晰程度】：高清\n"
        "【做種期限】：5种\n"
        "【下载软件】：qBittorrent\n"
        "【預覽圖片】：點擊小圖\n"
        "magnet:?xt=urn:btih:B625D381A482923F10B472BC8708069CE31B2030\n"
    )
    block = _assemble_subresource_block(
        paired="B625D381A482923F10B472BC8708069CE31B2030",
        name="[MP4/4.39G]ABW-112破壊版",
        scope=scope,
        field_lo=0,
        field_hi=len(scope),
        kind="film",
        lim=8,
        base_url="https://bbs.xfca2022.com/",
    )
    assert "【影片大小】：4.39G" in block.description
    assert "特" not in (block.description.split("【影片大小】：", 1)[-1].split("\n", 1)[0])
    assert "特徵" not in block.description.split("【影片大小】：", 1)[-1].split("\n", 1)[0]
    assert "健康度" not in block.description
    assert block.size > 0


def test_tid_26694474_html_size_labels_clean():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "_tmp_evolve_26694474.html"
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    dual = parse_thread_dual(
        html, preferred_link="magnet", tid=26694474, board_fid="103"
    )
    assert len(dual.assets) >= 30
    for a in dual.assets:
        lines = (a.description or "").splitlines()
        size_lines = [ln for ln in lines if ln.startswith("【影片大小】")]
        assert size_lines, a.filename
        val = size_lines[0].split("：", 1)[-1].strip()
        assert val
        assert "特徵" not in val and "特 徵" not in val
        assert "健康度" not in val
        assert "qBittorrent" not in val
        assert len(val) <= 16
