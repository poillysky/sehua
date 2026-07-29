"""子资源 filename：【影片名称】/【资源名称】，不是 ed2k/dn 链内名。"""

from __future__ import annotations

from parsers.resource_names import (
    filename_from_link,
    is_missing_filename,
    resolve_sub_filename,
    subtitle_from_description,
)


def test_missing_placeholder_magnet():
    assert is_missing_filename("magnet-A14DF085", hash_value="A14DF0858322")
    assert is_missing_filename("", hash_value="ABC")
    assert is_missing_filename(
        "ABCDEFabcdefABCDEF0123456789ABCDEF01234567",
        hash_value="ABCDEFabcdefABCDEF0123456789ABCDEF01234567",
    )
    assert not is_missing_filename("片子A.mp4")
    assert not is_missing_filename("国产合集.rar")


def test_short_title_accept_and_salvage():
    from parsers.resource_names import (
        is_acceptable_short_title,
        is_weak_subresource_name,
        salvage_short_subresource_name,
    )

    assert is_acceptable_short_title("油鬼子")
    assert is_acceptable_short_title("甲")
    assert is_acceptable_short_title("OM1")
    assert not is_acceptable_short_title("A")
    assert not is_acceptable_short_title("")
    assert salvage_short_subresource_name("  油鬼子  \n垃圾") == "油鬼子"
    assert salvage_short_subresource_name("A") == ""
    assert not is_weak_subresource_name("油鬼子", post_title="合集帖")
    assert is_weak_subresource_name("A", post_title="合集帖")
    assert is_weak_subresource_name("合集帖", post_title="合集帖")


def test_clip_keeps_mp4_capacity_prefix_with_dash():
    """[MP4/1.5G] -繁中片名：'-' 不是结构分隔，不得裁空后回落帖标题（tid 27446845）。"""
    from parsers.resource_names import clip_subresource_display_name

    raw = "[MP4/1.5G] -公雞俱樂部新人參戰全程無套-同房不換性癖好滿足區PART.2"
    clipped = clip_subresource_display_name(raw)
    assert "公雞俱樂部" in clipped
    assert "PART.2" in clipped


def test_clip_keeps_leading_nickname_bracket_dash():
    """tid=22924760：【白菜妹妹】-正文 / 【91晚晚】-… 不得裁空回落帖标题。"""
    from parsers.resource_names import clip_subresource_display_name

    cabbage = (
        "【白菜妹妹】- 影文并茂心中的白月光沦为多人胯下玩物 "
        "狗链乳夹调教女神 淫荡的内心迎接抽插精液灌射"
    )
    clipped = clip_subresource_display_name(cabbage)
    assert clipped.startswith("【白菜妹妹】")
    assert "影文并茂" in clipped

    wan = (
        "【91晚晚】- 身材一流非常火的刚下海新人 逼嫩人美水多又淫荡 "
        "操穴狂流白浆 不看后悔活超好期待后续更新[6V]"
    )
    clipped2 = clip_subresource_display_name(wan)
    assert clipped2.startswith("【91晚晚】")
    assert "刚下海新人" in clipped2

    # 真结构尾巴仍截
    with_tail = clip_subresource_display_name(cabbage + "【影片大小】：757MB")
    assert "影文并茂" in with_tail
    assert "影片大小" not in with_tail
    assert "757" not in with_tail


def test_clip_keeps_ascii_studio_bracket_prefix():
    """tid=23957210：【影片标题】：[スタジオVG] 片名… 勿把 スタジオ 当元数据尾巴裁成 '['。"""
    from parsers.resource_names import clip_subresource_display_name

    raw = "[スタジオVG] 3Dループアニメビフォアフ伝説女僧侶リリアの悲劇"
    clipped = clip_subresource_display_name(raw)
    assert clipped.startswith("[スタジオVG]")
    assert "リリア" in clipped


def test_clip_keeps_decorative_bracket_before_comma():
    """tid=26644722：??【新流】，正文… 逗号不是字段分隔，勿裁成只剩 ??。"""
    from parsers.resource_names import (
        clip_subresource_display_name,
        is_weak_subresource_name,
    )

    raw = "??【新流】，私人健身教练，约炮大神【黑杰克】付费无水印，淫乱病房，医院无套打炮实录"
    clipped = clip_subresource_display_name(raw)
    assert clipped.startswith("??【新流】")
    assert "私人健身教练" in clipped
    assert "黑杰克" in clipped
    assert not is_weak_subresource_name(clipped, post_title="合集帖")
    # 真结构字段（冒号分隔）仍截断
    with_fmt = clip_subresource_display_name(raw + "【影片格式】：MP4")
    assert "私人健身教练" in with_fmt
    assert "影片格式" not in with_fmt
    assert not with_fmt.endswith("MP4")


def test_resolve_keeps_subresource_title():
    assert (
        resolve_sub_filename(
            inner_name="【合集】片子甲",
            title="合集帖标题",
            hash_value="A" * 40,
            link_uri="ed2k://|file|inner.mp4|1|" + "A" * 32 + "|/",
        )
        == "【合集】片子甲"
    )


def test_resolve_rejects_ed2k_embedded_name():
    uri = "ed2k://|file|alone.mp4|9|" + "C" * 32 + "|/"
    assert (
        resolve_sub_filename(
            inner_name="alone.mp4",
            title="单资源帖",
            hash_value="C" * 32,
            link_uri=uri,
        )
        == "单资源帖"
    )


def test_resolve_uses_description_subtitle():
    uri = "ed2k://|file|pack.rar|9|" + "C" * 32 + "|/"
    assert (
        resolve_sub_filename(
            inner_name="pack.rar",
            title="帖子标题",
            hash_value="C" * 32,
            link_uri=uri,
            description="【资源名称】真·资源名\n【资源大小】1G",
        )
        == "真·资源名"
    )


def test_resolve_skips_title_fallback_when_description_has_real_name():
    """弱名(=帖标题)不得挡住 description 里的【影片名称】（tid=21973527 类误判）。"""
    title = "★●最新の中文字幕㊣↗️精彩合集↘️♀[09.27]"
    real = "[MIRD-260C]〜我是一个幻想发明家〜我要让布布键盘学院的女孩们的乳头变得敏感"
    got = resolve_sub_filename(
        inner_name=title,
        title=title,
        hash_value="A" * 40,
        description=f"【影片名称】：{real}\n【影片大小】：6.81GB\n【影片格式】：MP4",
    )
    assert got == real
    assert got != title


def test_resolve_skips_decoration_only_heart():
    """【影片名称】：❤️ 是装饰占位，不得当子名；无更好候选时才回落帖标题。"""
    from parsers.resource_names import is_decoration_only_filename, is_weak_subresource_name

    assert is_decoration_only_filename("❤️")
    assert is_decoration_only_filename("??")
    assert is_weak_subresource_name("❤️", post_title="合集帖")
    title = "合集帖标题"
    got = resolve_sub_filename(
        inner_name="❤️",
        title=title,
        hash_value="B" * 40,
        description="【影片名称】：❤️\n【影片大小】：2330MB",
    )
    assert got == title


def test_clip_keeps_heart_decorative_bracket_before_comma():
    """❤️【重磅群交】，正文… 不得被截成纯 ❤️（曾把中文逗号当结构分隔，tid=22128012）。"""
    from parsers.content import _clip_field_value
    from parsers.resource_names import clip_subresource_display_name, is_decoration_only_filename

    raw = (
        "❤️【重磅群交】，夫妻交流群线下聚会性轰趴群交三部曲，"
        "直击换妻淫乱现场，场面堪比岛国A片，超级淫乱(3V)"
    )
    clipped = clip_subresource_display_name(raw)
    assert "重磅群交" in clipped
    assert "超级淫乱" in clipped
    assert not is_decoration_only_filename(clipped)
    assert _clip_field_value(raw, label="影片名称").find("重磅群交") >= 0


def test_clip_keeps_decor_bracket_before_underscore():
    """64【海砂原创】_玩弄… 不得被截成 64（下划线不作结构分隔，tid=24592539）。"""
    from parsers.content import _clip_field_value
    from parsers.resource_names import clip_subresource_display_name

    raw = "64【海砂原创】_玩弄捆绑舞蹈系芭蕾少女极限驷马与对镜高抬腿sp惩罚"
    clipped = clip_subresource_display_name(raw)
    assert clipped == raw
    assert "海砂原创" in _clip_field_value(raw, label="影片名称")


def test_subtitle_from_description_prefers_film():
    assert (
        subtitle_from_description("【资源名称】甲\n【影片名称】乙")
        == "乙"
    )


def test_pick_keeps_nested_decorative_brackets():
    """片名里的【S级泄密】等装饰标签不得截断取值。"""
    from parsers.content import _subresource_title_value, extract_metadata
    from parsers.resource_names import pick_subresource_title

    text = (
        "【影片名称】：??【S级泄密】姿势很多的反差少妇露脸性爱，"
        "床上各种高潮脸窒息吐舌阿黑颜，无套中出母狗呻吟享受，原档无水印(22V)\n"
        "【影片格式】：MP4\n"
        "【影片大小】：917MB\n"
        "【影片时间】：34:25\n"
        "【影片说明】：无码\n"
        "【影片截图】："
    )
    want = (
        "??【S级泄密】姿势很多的反差少妇露脸性爱，"
        "床上各种高潮脸窒息吐舌阿黑颜，无套中出母狗呻吟享受，原档无水印(22V)"
    )
    assert pick_subresource_title(text, prefer_last=False) == want
    assert extract_metadata(text).get("影片名称") == want
    assert _subresource_title_value(text, 6, len(text)) == want


def test_pick_keeps_various_decorative_prefixes_and_brackets():
    """?? ※ ★ ！！ 全角？？ 以及异写括号字段，片名应完整保留。"""
    from parsers.content import extract_metadata
    from parsers.resource_names import pick_subresource_title

    cases = [
        (
            "【影片名称】：※※【内部流出】样片名甲\n［影片格式］：MP4\n",
            "※※【内部流出】样片名甲",
        ),
        (
            "【影片名称】：！！【S级】样片名乙\n「影片大小」：1.2GB\n",
            "！！【S级】样片名乙",
        ),
        (
            "［影片名称］：？？『黑料』样片名丙\n【影片说明】：无码\n",
            "？？『黑料』样片名丙",
        ),
        (
            "『资源名称』：★★【自转】合集丁(12V)\n【资源类型】：视频\n",
            "★★【自转】合集丁(12V)",
        ),
        (
            "【影片名称】:◆◆【完结】尾声戊\n【影片预览】：\n",
            "◆◆【完结】尾声戊",
        ),
    ]
    for text, want in cases:
        assert pick_subresource_title(text, prefer_last=False) == want, text
        meta = extract_metadata(text)
        got = meta.get("影片名称") or meta.get("资源名称")
        assert got == want, text


def test_resolve_falls_back_to_title():
    assert (
        resolve_sub_filename(
            inner_name="magnet-A14DF085",
            title="【BT】合集帖",
            hash_value="A14DF0858322ABCD",
        )
        == "【BT】合集帖"
    )


def test_filename_from_ed2k_link():
    uri = "ed2k://|file|demo视频.mp4|12345|AAAABBBBCCCCDDDDEEEEFFFF00001111|/"
    assert filename_from_link(uri) == "demo视频.mp4"


def test_persist_multi_and_single_naming(monkeypatch):
    from parsers.links import DualParseResult, ParsedAsset
    from db import persist as persist_mod

    class _Conn:
        def commit(self):
            return None

        def rollback(self):
            return None

    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)
    monkeypatch.setattr(persist_mod, "delete_stub_by_source_url", lambda *a, **k: False)
    monkeypatch.setattr(persist_mod, "sync_board_meta_by_source_url", lambda *a, **k: 0)

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append(
            {
                "filename": link.filename,
                "title": kwargs.get("title"),
                "hash": link.hash,
            }
        )
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)

    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename="片子甲真名",
            size=1,
            uri="magnet:?xt=urn:btih:" + "A" * 40 + "&dn=子文件A.mp4",
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename="magnet-BBBBBBBB",
            size=1,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
            is_primary=False,
        ),
    ]
    parsed = DualParseResult(
        tid=1,
        title="合集标题",
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
    )
    out = persist_mod.persist_dual_parse(
        _Conn(), parsed, source_url="https://x/thread-1-1-1.html"
    )
    assert out["count"] == 2
    assert calls[0]["title"] == "合集标题"
    assert calls[0]["filename"] == "片子甲真名"
    assert calls[1]["title"] == "合集标题"
    assert calls[1]["filename"] == "合集标题"  # 无名 → 标题

    calls.clear()
    alone = ParsedAsset(
        link_kind="ed2k",
        hash="C" * 32,
        filename="alone.mp4",
        size=9,
        uri="ed2k://|file|alone.mp4|9|" + "C" * 32 + "|/",
        is_primary=True,
    )
    parsed2 = DualParseResult(
        tid=2,
        title="单资源帖",
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=[alone],
        primary_link_kind="ed2k",
    )
    persist_mod.persist_dual_parse(
        _Conn(), parsed2, source_url="https://x/thread-2-1-1.html"
    )
    assert calls[0]["title"] == "单资源帖"
    # ed2k 链内名不是子资源名 → 退回主标题
    assert calls[0]["filename"] == "单资源帖"


def test_resolve_rejects_html_bbcode_and_intro_tail():
    from parsers.resource_names import (
        clip_subresource_display_name,
        is_dirty_filename,
        resolve_sub_filename,
    )

    htmlish = (
        '[url]www.98T.la@CLA96-Ai.mp4[/" target="_blank">'
        '<span class="__cf_email__" data-cfemail="abc">x</span></a>'
    )
    assert is_dirty_filename(htmlish)
    assert (
        resolve_sub_filename(
            inner_name=htmlish,
            title="【整理】cla合集标题",
            hash_value="A" * 40,
        )
        == "【整理】cla合集标题"
    )

    intro = (
        "《一半海水一半火焰》 【资源介绍】：看这部片子之前，我被朋友郑重告诫，"
        + ("很长正文" * 40)
    )
    clipped = clip_subresource_display_name(intro)
    assert clipped == "《一半海水一半火焰》"
    assert "资源介绍" not in clipped

    attach_ui = (
        "20e90e4390086.gif (1.63 MB, 下载次数: 0) 下载附件 2024-08-04 18:32 上传 "
        "c2ce21c5e77f2.gif (1.48 MB, 下载次数: 0)"
    )
    assert (
        resolve_sub_filename(
            inner_name=attach_ui,
            title="果冻传媒-性感女外教",
            hash_value="B" * 40,
        )
        == "果冻传媒-性感女外教"
    )

    jp = (
        "BD-M01 中出世界 EXCITE【AI增强】 中出しワールド EXCITE "
        "主演女優: 星優乃・浜崎ひめ スタジオ: ムゲン "
        + ("カテゴリで探す:完全無修正" * 8)
    )
    got = resolve_sub_filename(inner_name=jp, title="BD二部", hash_value="C" * 40)
    assert "主演女優" not in got
    assert "カテゴリ" not in got
    assert len(got) <= 200
    assert got.startswith("BD-M01")
