"""2048 抽样驱动的元数据归一 / 脏值清洗。"""

from parsers.content import (
    _clip_field_value,
    extract_metadata,
    normalize_metadata_for_board,
)


def test_clip_exclusive_structure_tail_labels():
    """独家帖【是否有水印】【目录树】须截断，避免 filename 顶满 255 仍含尾巴。"""
    raw = (
        "2048独家合集 气质御姐情趣慢摇【16gb/20v】 【是否有水印】:无 "
        "【资源大小/数量】:16gb/20v 【目录树】: --> --> 购买本帖会留有购买记录"
    )
    assert _clip_field_value(raw, label="影片名称") == "2048独家合集 气质御姐情趣慢摇【16gb/20v】"
    assert _clip_field_value(raw, label="资源名称") == "2048独家合集 气质御姐情趣慢摇【16gb/20v】"


def test_clip_filetype_label_boundary():
    raw = "FC2-PPV-4910529 受付嬢【高清無碼】 【文件类型】：MP4 【影片大小】：1.2G"
    assert _clip_field_value(raw, label="影片名称") == "FC2-PPV-4910529 受付嬢【高清無碼】"


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


def test_2048_exclusive_drops_fake_film_name_from_title():
    """tid=27097301：正文【资源名称】真名；勿再用帖标题灌【影片名称】（带 2048独家合集）。"""
    from parsers.content import (
        build_structured_description,
        strip_2048_exclusive_title_prefix,
    )
    from parsers.resource_names import resolve_sub_filename, subtitle_from_description

    title = (
        "2048独家合集 极品身材御姐【linjianvhai】连体情趣制服丝袜"
        "灌肠扣逼扩阴器特写非常淫荡5月23日-6月22日part4【27V/26GB】"
    )
    real = (
        "极品身材御姐【linjianvhai】连体情趣制服丝袜"
        "灌肠扣逼扩阴器特写非常淫荡5月23日-6月22日part4【27V/26GB】"
    )
    assert strip_2048_exclusive_title_prefix(title) == real

    desc = build_structured_description(
        {"资源名称": real, "是否有水印": "无码/有水印"},
        title=title,
        board_fid="3",
    )
    assert "【资源名称】" in desc
    assert "【影片名称】" not in desc
    assert "2048独家合集" not in desc

    # 旧库双字段 description 也应解析出真名
    legacy = f"【影片名称】：{title}\n【资源名称】：{real}"
    assert subtitle_from_description(legacy) == real
    assert (
        resolve_sub_filename(
            inner_name="",
            title=title,
            description=legacy,
            hash_value="A" * 40,
        )
        == real
    )
