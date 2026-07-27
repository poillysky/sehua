"""结构标签字间空格：影片名称/大小等（不限特征码）。"""

from parsers.content import (
    extract_metadata,
    extract_subresource_blocks,
    iter_subresource_title_spans,
)
from parsers.links import parse_thread_dual
from parsers.magnet import parse_capacity_bytes, parse_magnet_text
from parsers.thread_gates import has_target_link


def test_spaced_film_name_and_size_metadata_and_blocks():
    h1 = "A" * 40
    h2 = "B" * 40
    html = f"""
    <div class="t_f" id="postmessage_1">
    【影 片 名 称】：测试片名甲
    【影 片 大 小】：1.2G
    【影 片 格 式】：MP4
    magnet:?xt=urn:btih:{h1}
    【影 片 名 称】：测试片名乙
    【影 片 大 小】：2.3G
    magnet:?xt=urn:btih:{h2}
    </div>
    """
    meta = extract_metadata(
        "【影 片 名 称】：测试片名甲\n【影 片 大 小】：1.2G\n【影 片 格 式】：MP4\n"
    )
    assert meta.get("影片名称") == "测试片名甲"
    assert meta.get("影片大小") == "1.2G"
    assert meta.get("影片格式") == "MP4"

    spans = iter_subresource_title_spans(html)
    assert len(spans) == 2

    blocks = extract_subresource_blocks(
        html, {h1, h2}, base_url="https://www.sehuatang.net/"
    )
    assert len(blocks) == 2
    assert blocks[0].title == "测试片名甲"
    assert blocks[0].size == parse_capacity_bytes("1.2G")
    assert blocks[1].title == "测试片名乙"
    assert blocks[1].size == parse_capacity_bytes("2.3G")

    dual = parse_thread_dual(html, preferred_link="magnet", tid=1, board_fid=2)
    assert len(dual.assets) == 2
    names = {a.filename for a in dual.assets}
    assert "测试片名甲" in names
    assert "测试片名乙" in names


def test_dot_spaced_resource_name_and_size():
    h = "C" * 40
    raw = f"【资·源·名·称】：合集子项\n【资.源.大.小】：899M\nmagnet:?xt=urn:btih:{h}"
    assert has_target_link(raw, "magnet")
    assert len(parse_magnet_text(raw)) == 1
    meta = extract_metadata(raw)
    assert meta.get("资源名称") == "合集子项" or meta.get("資源名稱") == "合集子项"
    assert meta.get("资源大小") == "899M" or meta.get("資源大小") == "899M"
    assert parse_capacity_bytes(raw) == parse_capacity_bytes("899M")
