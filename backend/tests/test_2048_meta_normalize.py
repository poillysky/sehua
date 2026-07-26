"""2048 抽样驱动的元数据归一 / 脏值清洗。"""

from parsers.content import (
    _clip_field_value,
    extract_metadata,
    normalize_metadata_for_board,
)


def test_clip_size_strips_fullwidth_colon_and_url():
    assert _clip_field_value("︰5.23GB", label="文件大小") == "5.23GB"
    assert (
        _clip_field_value(
            "5.15GB https://www.rmdown.com/link.php?hash=262abc",
            label="影片大小",
        )
        == "5.15GB"
    )


def test_extract_drops_bogus_torrent_name_and_preview():
    text = (
        "【种子名称】：]ent\n"
        "【影片大小】：1.48GB\n"
        "【影片预览】：下载磁链：磁力链接\n"
        "【影片标题】：heyzo 3787 测试片名\n"
    )
    meta = extract_metadata(text)
    assert "种子名称" not in meta
    assert meta.get("影片大小") == "1.48GB"
    assert "影片预览" not in meta
    assert meta.get("影片标题") == "heyzo 3787 测试片名"


def test_normalize_2048_aliases_and_drop_hash_labels():
    raw = {
        "影片標題": "中文片名A",
        "是否有碼": "無碼",
        "檔案大小": "︰1.09GB",
        "試證全碼": "F748E8A984DB7AD3A01F6D88136D40B351C72B5C",
        "种子名称": "]ent",
        "圖片預覽": "https://www.rmdown.com/link.php?hash=262a287c790ac45cc771947fa0ab7064e9b09860",
    }
    out = normalize_metadata_for_board(raw, board_fid="4")
    assert out.get("影片名称") == "中文片名A"
    assert out.get("是否有码") == "無碼"
    assert out.get("影片大小") == "1.09GB"
    assert "試證全碼" not in out and "试证全码" not in out
    assert "种子名称" not in out
    assert "图片预览" not in out
