"""子版 key（fid:typeid）应落到主板块结构卡片。"""

from parsers.content import build_structured_description, description_profile_for_board


def test_description_profile_strips_typeid():
    bt = description_profile_for_board("151")
    subunit = description_profile_for_board("151:823")
    anime = description_profile_for_board("39:404")
    assert bt["title_as"] == "影片名称"
    assert subunit["title_as"] == "影片名称"
    assert anime["title_as"] == "影片名称"
    assert "出演女优" in subunit["labels"]


def test_build_description_bt_with_subunit_key():
    meta = {
        "影片名称": "测试片名",
        "出演女优": "某某",
        "影片容量": "1.2GB",
        "是否有码": "无码",
        "影片格式": "MP4",
        "解压密码": "1234",
    }
    desc = build_structured_description(meta, board_fid="151:823")
    assert "【影片名称】：测试片名" in desc
    assert "【出演女优】：某某" in desc
    assert "【是否有码】：无码" in desc
    assert "【资源名称】" not in desc
