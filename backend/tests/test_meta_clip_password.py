# -*- coding: utf-8 -*-
"""短枚举勿吞营销行；CF 密码在块内卡片也要还原。"""

from __future__ import annotations

from parsers.content import (
    enrich_block_with_cards,
    extract_metadata,
    extract_password,
    parse_thread_content,
)
from parsers.links import parse_thread_dual


def _encode_cf_email(plain: str, key: int = 0x5A) -> str:
    out = f"{key:02x}"
    for ch in plain.encode("utf-8"):
        out += f"{ch ^ key:02x}"
    return out


def test_sound_field_not_swallow_marketing_line():
    blob = (
        "【影片有无声音】：有\n"
        "某房7月13日原版 ￥12\n"
        "【剧情连拍截图/缩略图】\n"
        "98 (2).png (965.37 KB,\n"
        "【资源预览】\n"
        "98 (3).png (1.01 MB,\n"
    )
    meta = extract_metadata(blob)
    assert meta.get("影片有无声音") == "有"
    assert "某房" not in (meta.get("影片有无声音") or "")
    # 预览/截图字段不应把附件文件名当值
    assert not (meta.get("资源预览") or "").strip() or "png" not in (
        meta.get("资源预览") or ""
    ).lower()
    assert "png" not in (meta.get("剧情连拍截图缩略图") or "").lower()
    assert "png" not in (meta.get("剧情连拍截图/缩略图") or "").lower()


def test_div_newline_keeps_field_lines_like_human():
    """</div><div> 分行应像人眼一样切开，不靠短枚举兜底。"""
    from parsers.content import _clean_text

    html = (
        '<div align="center"><font size="2">【影片有无声音】：有</font></div>'
        '<div align="center"><font color="#ff00">某房7月13日原版 ￥12</font></div>'
        '<div align="center"><font size="2">【时间长度】：3小时</font></div>'
    )
    text = _clean_text(html)
    lines = text.split("\n")
    assert any(ln.endswith("有") and "某房" not in ln for ln in lines)
    assert any("某房" in ln and "有无声音" not in ln for ln in lines)
    meta = extract_metadata(text)
    assert meta.get("影片有无声音") == "有"
    assert meta.get("时间长度") == "3小时"


def test_soft_wrap_name_joins_hard_break_marketing_stops():
    """过长折行并入片名；营销硬换行不并入。"""
    from parsers.structure_cards import clip_card_value_lines, parse_structure_cards

    soft = (
        "【资源名称】：【自转】【百度/115】许墨探花26.07.06偷拍真实高端外围美腿续\n"
        "美腿学妹 微肉学姐继续很长一段不会单独成字段\n"
        "【资源类型】：视频\n"
    )
    cards = {c.raw_label: c for c in parse_structure_cards(soft)}
    assert "美腿学妹" in cards["资源名称"].value
    assert "视频" == cards["资源类型"].value

    hard = (
        "【影片有无声音】：有\n"
        "某房7月13日原版 ￥12\n"
        "【时间长度】：3小时\n"
    )
    assert clip_card_value_lines("other", "有\n某房7月13日原版 ￥12") == "有"
    meta = extract_metadata(hard)
    assert meta.get("影片有无声音") == "有"
    assert "某房" not in (meta.get("影片有无声音") or "")

    joined = clip_card_value_lines(
        "name",
        "超级美少女、\n无敌潮喷屁股怼镜头",
    )
    assert "无敌潮喷" in joined


def test_password_harvest_from_scattered_places():
    """密码须有标注；文末/无【】/附件语料可收；裸 98T 水印不猜。"""
    from parsers.content import harvest_extract_password, parse_thread_content
    from parsers.links import parse_thread_dual

    # 文末才写，且无【解压密码】标签
    late = (
        "【资源名称】：演示片\n"
        "【资源类型】：视频\n"
        "一堆剧情说明……\n"
        "解压请用这个 密码：sakura99\n"
    )
    assert harvest_extract_password(late) == "sakura99"

    # 裸 www.98T.la@（无密码标注）→ 不猜；预览附件名前缀同理
    assert harvest_extract_password("下载后自行解压 www.98T.la@ 即可") == ""
    assert (
        harvest_extract_password(
            "www.98t.la@【原相机泄密】肉肉.jpg (329.59 KB, 下载次数: 0)\n"
            "ed2k://|file|www.98t.la@demo.zip|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/"
        )
        == ""
    )

    # 「密码错误」不得误吞
    assert harvest_extract_password("提示：密码错误请重试") == ""

    # 人一眼能认：紧贴 / 空格 / 短中文口令 / 解压用
    assert harvest_extract_password("本帖密码sakura99可用") == "sakura99"
    assert harvest_extract_password("解压 密码 MyPass_01 即可") == "MyPass_01"
    assert harvest_extract_password("【说明】密码：天地玄黄") == "天地玄黄"
    assert harvest_extract_password("解压用www.98T.la@") == "www.98T.la@"
    assert harvest_extract_password("解压请用这个 密码：sakura99") == "sakura99"

    # 楼主二楼「钥匙：」——口令可为整段论坛链（tid=2983626），勿在 ? 截断
    key_url = (
        "sehuatang.net/forum.php?mod=viewthread&tid=2978299&extra=&page=1"
    )
    assert harvest_extract_password(f"钥匙：{key_url}") == key_url
    assert harvest_extract_password(f"钥匙:{key_url}") == key_url
    assert (
        harvest_extract_password(
            "防机器人搬运防盗门钥匙在2楼!\n"
            f"钥匙：{key_url}\n"
            "记住我的头像"
        )
        == key_url
    )
    # 无冒号的「钥匙在2楼」不是口令标注
    assert harvest_extract_password("防盗门钥匙在2楼!") == ""


def test_clip_password_value_end_boundaries():
    """口令吃到结束信号为止：完整提取、不吞说明。"""
    from parsers.content import clip_password_value, harvest_extract_password

    assert clip_password_value("www.98T.la@\n【文件大小】：1G") == "www.98T.la@"
    assert clip_password_value("1998@www.98T.la【资源类型】：视频") == "1998@www.98T.la"
    assert clip_password_value("www.98T.la@，需要把后面删除") == "www.98T.la@"
    assert clip_password_value("www.98T.la@才能打开") == "www.98T.la@"
    # @ 后账号含中文品牌（tid=2229054 橙子整理）；空格后说明不吞
    assert (
        clip_password_value("www.98t.la@lsp橙子 搬运无告知") == "www.98t.la@lsp橙子"
    )
    assert (
        harvest_extract_password("解压密码： www.98t.la@lsp橙子 搬运无告知“ 司马 ”")
        == "www.98t.la@lsp橙子"
    )
    # @ 后日文名（tid=2575947）；HTML 拆成 www.98T.la</a>@小野りんか
    assert clip_password_value("www.98T.la@小野りんか") == "www.98T.la@小野りんか"
    assert (
        harvest_extract_password("密码： www.98T.la @小野りんか")
        == "www.98T.la@小野りんか"
    )
    assert (
        harvest_extract_password("压缩包密码：www.98T.la@小野りんか")
        == "www.98T.la@小野りんか"
    )
    # 皮卡丘：【资源密码】：@品牌www.98T.la@（域名拆链夹空白，tid=2990288）
    assert (
        clip_password_value("@皮卡丘_剑染红尘 www.98T.la @")
        == "@皮卡丘_剑染红尘www.98T.la@"
    )
    assert (
        harvest_extract_password("【资源密码】：@皮卡丘_剑染红尘 www.98T.la @")
        == "@皮卡丘_剑染红尘www.98T.la@"
    )
    assert harvest_extract_password("【资源密码】：@") == ""
    assert clip_password_value("sakura99 解压后可用") == "sakura99"
    assert clip_password_value("pass123 demo.rar (1 KB") == "pass123"
    assert clip_password_value("MyBigDick@host 18OnlyGirls.rar (42 KB") == "MyBigDick@host"

    assert (
        harvest_extract_password(
            "解压密码是www.98T.la@，需要把后面《删除》这俩字删掉"
        )
        == "www.98T.la@"
    )
    assert (
        harvest_extract_password(
            "【解压密码】：1998@www.98T.la\n【文件大小】：1.05G"
        )
        == "1998@www.98T.la"
    )
    assert harvest_extract_password("密码：sakura99\ned2k://|file|a|1|AA|/") == "sakura99"
    assert harvest_extract_password("本帖密码sakura99可用") == "sakura99"

    key_url = (
        "sehuatang.net/forum.php?mod=viewthread&tid=2978299&extra=&page=1"
    )
    assert clip_password_value(f"{key_url} 即可解压") == key_url
    assert clip_password_value(f"{key_url}【资源类型】：视频") == key_url
    # 旧逻辑会在 ? 处截成 forum.php；钥匙链须整段保留
    assert clip_password_value(key_url) == key_url

    # 附件语料里才有
    html = """
    <html><body>
    <div id="postmessage_1">【资源名称】：只有链
    ed2k://|file|a.zip|100|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/
    </div></body></html>
    """
    parsed = parse_thread_dual(
        html,
        tid=900010,
        preferred_link="ed2k",
        extra_text="解压密码：www.98T.la@",
        board_fid=2,
    )
    assert parsed.extract_password == "www.98T.la@"
    assert "www.98T.la@" in (parsed.description or "")

    # 结构字段区没有，段落中有「解压密码是…」
    html2 = """
    <html><body><div id="postmessage_1">
    【资源名称】：甲
    【资源类型】：视频
    说明：本资源需要解压密码是www.98T.la@才能打开
    </div></body></html>
    """
    c = parse_thread_content(html2, tid=900011)
    assert c.extract_password == "www.98T.la@"


def test_block_enrich_restores_cf_password_and_clips_sound():
    plain = "1998@www.98T.la"
    enc = _encode_cf_email(plain)
    html_chunk = f"""
    <div>【资源名称】：许墨探花演示
    【资源类型】：视频
    【是否有码】：无码
    【解压密码】：<a href="/cdn-cgi/l/email-protection" class="__cf_email__"
      data-cfemail="{enc}">[email&#160;protected]</a>
    【文件大小】：3V/2.87G/1配额
    【影片有无声音】：有</font></div>
    <div><font color="#ff00">某房7月13日原版 ￥12</font></div>
    <div>【资源预览】</div>
    <div>98 (3).png (1.01 MB, 下载次数: 0)</div>
    """
    enriched = enrich_block_with_cards(html_chunk, kind="resource", board_fid=2)
    assert enriched.metadata.get("解压密码") == plain
    assert enriched.metadata.get("影片有无声音") == "有"
    assert "某房" not in (enriched.metadata.get("影片有无声音") or "")
    assert "png" not in (enriched.metadata.get("资源预览") or "").lower()
    assert plain in (enriched.description or "")


def test_tid3635420_style_dual_password_in_desc():
    plain = "1998@www.98T.la"
    enc = _encode_cf_email(plain)
    h = "08E06E238A7676E6B44C42364934ADB8"
    html = f"""
    <html><head><title>【自转】许墨探花演示【5V/1.73G/1配额】</title></head><body>
    <div id="postmessage_1">
      【资源名称】：【自转】许墨探花演示【5V/1.73G/1配额】
      【资源类型】：视频
      【是否有码】：无码
      【有无第三方水印】：有
      【解压密码】：
      <a href="/cdn-cgi/l/email-protection#abc" class="__cf_email__" data-cfemail="{enc}">
        <span class="__cf_email__" data-cfemail="{enc}">[email&#160;protected]</span>
      </a>
      【文件大小】：3V/2.87G/1配额
      【时间长度】：3小时
      【影片有无声音】：有
      <font color="#ff00">某房7月13日原版 ￥12</font>
      【剧情连拍截图/缩略图】
      <img file="https://cdn.example/a.png" src="https://cdn.example/t.png" />
      【资源预览】
      <img file="https://cdn.example/b.png" src="https://cdn.example/tb.png" />
      ed2k://|file|demo.zip|1868792639|{h}|/
    </div>
    </body></html>
    """
    content = parse_thread_content(html, tid=3635420)
    assert content.extract_password == plain
    assert content.metadata.get("影片有无声音") == "有"

    parsed = parse_thread_dual(html, tid=3635420, preferred_link="ed2k", board_fid=2)
    assert parsed.extract_password == plain
    assert (parsed.metadata or {}).get("影片有无声音") == "有"
    assert "某房" not in ((parsed.metadata or {}).get("影片有无声音") or "")
    assert "png" not in ((parsed.metadata or {}).get("资源预览") or "").lower()
    assert plain in (parsed.description or "") or plain in (
        (parsed.assets[0].description if parsed.assets else "") or ""
    )
    assert extract_password("", parsed.metadata) == plain or parsed.extract_password == plain
