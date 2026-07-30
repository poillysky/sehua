"""ed2k 板块应接受磁力链接。"""

from __future__ import annotations

from parsers.magnet import normalize_magnet_corpus, parse_magnet_text
from parsers.thread_gates import has_target_link, is_non_target_cloud_share
from workers.thread_outcome import judge_thread_html


MAGNET = (
    "magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01"
    "&dn=sample"
)


def test_has_target_link_ed2k_accepts_magnet():
    assert has_target_link(MAGNET, "ed2k")
    assert not has_target_link("https://pan.baidu.com/s/abc", "ed2k")
    assert has_target_link("ed2k://|file|a.mkv|1|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/", "ed2k")


def test_has_target_link_magnet_accepts_ed2k():
    """磁力板也认正文 ed2k（转帖区【115ed2k】常见）。"""
    ed2k = "ed2k://|file|a.mkv|1|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/"
    assert has_target_link(ed2k, "magnet")
    assert has_target_link(MAGNET, "magnet")


def test_parse_magnet_multi_query_params():
    """URI 可带多个 & 参数（dn + xl），且单段有界。"""
    h = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
    raw = f"magnet:?xt=urn:btih:{h}&dn=demo.mp4&xl=1234567890&tr=udp://tracker.example/announce"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert links[0].size == 1234567890


def test_incomplete_ed2k_not_target_link():
    """缺 hash 的半截 ed2k / d2k 不应算有目标链（常见发帖截断）。"""
    broken = "ed2k://|file|www.98T.la@demo.zip|509285037|"
    broken_d2k = "d2k://|file|www.98T.la@demo.zip|509285037|"
    assert not has_target_link(broken, "ed2k")
    assert not has_target_link(broken_d2k, "ed2k")
    assert is_non_target_cloud_share(
        link_kind="ed2k",
        text=broken + "\nhttps://pan.baidu.com/s/1abcDEF?pwd=xxxx",
    )


def test_cloud_share_not_when_magnet_present():
    text = f"网盘 https://pan.baidu.com/s/xxx\n{MAGNET}"
    assert not is_non_target_cloud_share(link_kind="ed2k", text=text)


def test_parse_fullwidth_colon_magnet():
    """中文全角冒号 magnet：?xt=urn：btih：… 应能解析。"""
    raw = "magnet：?xt=urn：btih：33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    assert "magnet:?" in normalize_magnet_corpus(raw)
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    assert has_target_link(raw, "ed2k")
    assert has_target_link(raw, "magnet")


def test_parse_colonless_magnet_anti_filter():
    """附件防和谐去冒号：magnetxt=urnbtih:HASH 应还原。"""
    raw = (
        "magnetxt=urnbtih:2C01890375D5F1D3C91DA109F807EB680FD38D9D\n"
        "magnetxt=urnbtih:7B9851F0E832003BD5CE0B845D3D06D44CE49EA2"
    )
    fixed = normalize_magnet_corpus(raw)
    assert "magnet:?xt=urn:btih:2C01890375D5F1D3C91DA109F807EB680FD38D9D" in fixed
    links = parse_magnet_text(raw)
    assert len(links) == 2
    assert links[0].infohash == "2C01890375D5F1D3C91DA109F807EB680FD38D9D"
    assert has_target_link(raw, "ed2k")
    assert has_target_link(raw, "magnet")


def test_parse_bare_infohash_after_copy_code():
    """Discuz「复制代码下载：」后的裸 infohash（tid 3533954 类）。"""
    h = "f7809dc8bf32d7be01b6d89b5fb31e3af1a37c5a"
    raw = f"复制代码下载：{h}"
    fixed = normalize_magnet_corpus(raw)
    assert f"magnet:?xt=urn:btih:{h}" in fixed
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert links[0].link.lower().startswith("magnet:?xt=urn:btih:")
    assert has_target_link(raw, "magnet")
    assert has_target_link(raw, "ed2k")


def test_parse_bare_infohash_in_blockcode_html():
    """blockcode 标题「复制代码」与 hash 分行时也能识别。"""
    h = "F7809DC8BF32D7BE01B6D89B5FB31E3AF1A37C5A"
    html = f"""
    <div class="blockcode">
      <em>复制代码</em>
      <ol><li>{h}</li></ol>
    </div>
    """
    links = parse_magnet_text(html)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(html, "magnet")


def test_bare_hex_without_cue_not_magnet():
    """无提示语的裸 40 位 hex 不误判（避免正文噪音）。"""
    raw = "校验 f7809dc8bf32d7be01b6d89b5fb31e3af1a37c5a 结束"
    assert parse_magnet_text(raw) == []
    assert not has_target_link(raw, "magnet")


def test_title_bt_magnet_label_does_not_redos():
    """标题仅有【BT/磁力】时不得扫整页卡死（回归：裸线索 ReDoS）。"""
    import time

    h = "ca0d5b474a8b3fef00ebb8abec6e67b713f59765"
    # 大量残缺标签，旧正则会回溯爆炸
    bomb = "<" * 8000
    raw = f"【BT/磁力】私密电报群泄密测试{bomb}无哈希"
    t0 = time.perf_counter()
    assert parse_magnet_text(raw) == []
    assert time.perf_counter() - t0 < 1.0
    # 仍能识别真正的【哈希校验】
    raw2 = f"【BT/磁力】标题{bomb[:200]}【哈希校验】：{h}"
    t0 = time.perf_counter()
    links = parse_magnet_text(raw2)
    assert time.perf_counter() - t0 < 1.0
    assert len(links) == 1
    assert links[0].infohash == h.upper()


def test_parse_bare_infohash_hash_check_label():
    """【哈希校验】后的裸 infohash（tid 3628517 类）。"""
    h = "ca0d5b474a8b3fef00ebb8abec6e67b713f59765"
    raw = f"""
    【影片名称】：测试片子
    【影片大小】：508MB
    【哈希校验】：{h}
    【是否有码】：无码
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert links[0].link.lower() == f"magnet:?xt=urn:btih:{h}"
    assert "测试片子" in links[0].filename
    assert "是否有码" not in links[0].link
    assert has_target_link(raw, "magnet")


def test_parse_bare_infohash_fullwidth_hash_label_2048():
    """2048 国内原创：【ＨＡＳＨ】全角拉丁 + 裸 infohash（tid 27437738）。"""
    h = "411575f9068635c8c80f2ce655ec75a789b645f2"
    raw = f"""
    【檔案名稱】:测试片子
    【檔案大小】:1.98G
    【ＨＡＳＨ】:{h}
    【製作說明】:僅限於寬頻測驗
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")
    # 半角【HASH】同样可认
    links2 = parse_magnet_text(f"【HASH】：{h}")
    assert len(links2) == 1 and links2[0].infohash == h.upper()


def test_parse_bare_infohash_feature_code_label():
    """【特征编码】后的裸 infohash（tid 2856358 类）。"""
    h = "40426ff87ad87231c4f12fcca32f512e80bc1f11"
    raw = f"""
    【影片名称】：测试片子
    【影片大小】：70.9 M
    【特征编码】：{h}
    【是否有码】：无码
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert links[0].link.lower() == f"magnet:?xt=urn:btih:{h}"
    assert "测试片子" in links[0].filename
    assert has_target_link(raw, "magnet")


def test_parse_bare_infohash_feature_full_code_2048():
    """2048【特征全码】裸 infohash。"""
    h = "D83CC2E432A10E0519282017BB68DA4884E135C8"
    raw = f"""
    【影片名称】：测试片子
    【影片大小】：1.62GB
    【特征全码】：{h}
    【作种期限】：做種7天
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_incomplete_feature_full_code_is_abnormal_skip():
    """tid 3027518：【特徵全碼】仅 31 hex → 异常下载链接，勿 need_attachments。"""
    from parsers.magnet import has_abnormal_download_link
    from workers.thread_outcome import judge_thread_html

    bad = "DEA4FA78748AAD5FEAE404E9F17AA45"  # 31
    assert len(bad) == 31
    raw = f"""
    <html><head><title>测试异常特征码</title></head>
    <body><div id="postmessage_1" class="t_f">
    【影片名称】：残缺特征码片子
    【影片大小】：1.2GB
    【特徵全碼】：{bad}
    </div></body></html>
    """
    assert has_abnormal_download_link(raw) is True
    assert has_target_link(raw, "magnet") is False
    out = judge_thread_html(
        raw,
        board_fid=2,
        list_title="测试异常特征码",
        preferred_link="magnet",
        forum_id="sehuatang",
        tid=3027518,
    )
    assert out.verdict == "skipped"
    assert out.outcome == "非资源（跳过）"
    assert out.need_attachments is False


def test_complete_feature_code_not_abnormal():
    from parsers.magnet import has_abnormal_download_link

    h40 = "D83CC2E432A10E0519282017BB68DA4884E135C8"
    assert has_abnormal_download_link(f"【特徵全碼】：{h40}") is False
    h32 = "A" * 32
    assert has_abnormal_download_link(f"【特征编码】：{h32}") is False


def test_parse_bare_infohash_typo_shizheng_same_line_as_size():
    """2048 错别字【试证全码】与资源大小同行（tid 27431995）。"""
    h = "6C92A52EF6175D85563AD87644B297CB16C26E86"
    raw = f"""
    【资源名称】：▲tj1221▲FC2新片素人合集[07.25] | 最新合集
    【资源类型】：MP4
    【资源大小】：0.95GB 【试证全码】：{h}
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_seed_feature_code_hash_check_semicolon_2048():
    """2048【种子特码】：哈希校验; HASH; ;（tid 27433099）。"""
    h = "98f092a5ab5bbb846785250ac4137a123fe8cdb2"
    raw = f"""
    【影片名称】：新FC2PPV 4713971
    【影片大小】：2.04G
    【种子期限】：高速做种三日
    【种子特码】：哈希校验; {h}; ;
    【下载说明】：qBittorrent
    https://www.rmdown.com/link.php?hash=26{h}
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_downsx_torrent_path_hash():
    """色花堂旧合集：仅 downsX /torrent/{infohash}，无 magnet 正文（tid 547624）。"""
    h1 = "E6FA5EACD180AC430A4F6466D98E1641A68DAEAD"
    h2 = "8132FDB7857E55B54CE76C7F6D71286EBE322C89"
    raw = f"""
    【影片名称】：片子A
    https://www1.downsx.pw/torrent/{h1}
    【影片名称】：片子B
    https://www1.downsx.pw/torrent/{h2}
    """
    links = parse_magnet_text(raw)
    assert {x.infohash for x in links} == {h1, h2}
    assert has_target_link(raw, "magnet")


def test_parse_download_address_bare_infohash():
    """色花堂【磁力链接】帖：【下载地址】后直接跟 40 位 hash（tid 1224229）。"""
    h = "e64776f87ac8657ca084045d44c766d57a4c2386"
    raw = f"""
    【资源名称】：stars-779
    【文件大小】：1.44GB
    【下载地址】：{h}
    【収録時間】：121分
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_bare_infohash_verify_full_code_2048():
    """2048【驗證全码】裸 infohash。"""
    h = "0c5ae2d3436fcd2bd4359bafdde3bd65ec835deb"
    raw = f"""
    【影片名稱】：测试片子
    【影片大小】：3.71GB
    【驗證全码】：{h}
    【作種期限】：做種5天
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_extract_title_strips_2048_board_suffix():
    from parsers.content import extract_title

    # <title> 去站名/板块后缀
    assert (
        extract_title("<title>♀合集♀[06.13] | 最新合集</title>")
        == "♀合集♀[06.13]"
    )
    assert (
        extract_title(
            "<title>★●亚洲无码[06.13] | 最新合集 - 人人为我论坛</title>"
        )
        == "★●亚洲无码[06.13]"
    )
    # thread_subject 按页面原文，不去「| 最新合集」
    assert (
        extract_title('<a id="thread_subject">片名 | 最新合集</a>')
        == "片名 | 最新合集"
    )


def test_parse_magnet_infohash_split_by_ideographic_comma():
    """色花堂 blockcode 把顿号塞进 hash（tid 1540160）。"""
    h = "67745fc1f43dbc15d347cd80c226835de33c01fd"
    raw = (
        "【资源名称】：FC2-PPV-3775668\n"
        "【下载链接】：\n"
        f"magnet:?xt=urn:btih:67745fc、1f43dbc15d347cd80c226835de33c01fd\n"
        "复制代码\n"
        "【文件大小】：【2.7g】\n"
    )
    fixed = normalize_magnet_corpus(raw)
    assert f"magnet:?xt=urn:btih:{h}" in fixed.lower()
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_bare_infohash_verify_number_vertical_colon_sehua():
    """色花堂【驗證編號】︰hash（U+FE30 竖排冒号，tid 1537403）。

    漏认会误走附件下载；认出后单资源帖直接入库，无需下种子。
    """
    h = "28d281aba2ecad0c13f03843c6e6894c79a78043"
    raw = (
        "【影片名稱】︰我選你~來看我的穴\n"
        "【影片大小】︰601 MB\n"
        f"【驗證編號】︰{h}\n"
        "【圖片預覽】︰\n"
        "10musume-090623_01-FHD.torrent\n"
    )
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")

    from workers.thread_outcome import judge_thread_html

    html = f"<div class='t_f' id='postmessage_1'>{raw}</div>"
    # 附件区存在也不该 need_attachments
    html += (
        "<ignore_js_op><a href='forum.php?mod=attachment&aid=1'>"
        "10musume-090623_01-FHD.torrent</a></ignore_js_op>"
    )
    out = judge_thread_html(
        html,
        board_fid=2,
        list_title="[FHD] sample",
        base_url="https://www.sehuatang.net/thread-1537403-1-1.html",
        preferred_link="magnet",
    )
    assert out.verdict == "import"
    assert out.need_attachments is False


def test_parse_magnet_btih_wrapped_in_escaped_span():
    """blockcode 把 hash 包进 &lt;span&gt;（tid 3094851 磁力+特征编码同帖）。"""
    h = "bd0be9bbbf9775c1aaeacbf1c3f957371f51542a"
    raw = (
        "【磁力链接】: "
        f"magnet:?xt=urn:btih:&lt;span style=&quot;background-color: rgb(255, 255, 255);&quot;&gt;{h}&lt;/span&gt;"
    )
    fixed = normalize_magnet_corpus(raw)
    assert f"magnet:?xt=urn:btih:{h}" in fixed.lower()
    assert "&lt;span" not in fixed.lower()
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_feature_code_and_magnet_same_hash_dedupe():
    """特征编码裸 hash 与磁力 URI 同值时只保留一条。"""
    h = "bd0be9bbbf9775c1aaeacbf1c3f957371f51542a"
    raw = f"""
    【影片名称】：同帖双写
    【特征編碼】：{h}
    【磁力链接】: magnet:?xt=urn:btih:{h}
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert "同帖双写" in links[0].filename


def test_parse_seed_feature_code_and_dated_magnet():
    """【种子特码】+ magnet:?xt=urn:btih:YYYYMM/HASH（tid 3286293）。"""
    h = "0d76c369f18439e7a8458f1ca904d514e321dc58"
    raw = f"""
    【影片名称】：合集其一
    【种子特码】：{h}
    【磁力链接】: magnet:?xt=urn:btih:202601/{h}&dn=demo
    """
    fixed = normalize_magnet_corpus(raw)
    assert f"magnet:?xt=urn:btih:{h}" in fixed.lower()
    assert "202601/" not in fixed.split("btih:")[-1][:20]
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert "合集其一" in links[0].filename
    assert has_target_link(raw, "magnet")

    for lab in ("種子特碼", "种子特碼", "種子特码"):
        got = parse_magnet_text(f"【{lab}】：{h}")
        assert len(got) == 1 and got[0].infohash == h.upper(), lab


def test_parse_verify_code_label():
    """【驗證編號】裸 infohash（tid 2707462）。"""
    h = "15427948b1a625fea4ce410e480a53c017c4c985"
    raw = f"""
    【影片名称】：验证编号样例
    【影片大小】：1.2G
    【驗證編號】：{h}
    """
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h.upper()
    assert "验证编号样例" in links[0].filename
    assert has_target_link(raw, "magnet")


def test_parse_feature_verify_all_recorded_combos():
    """实录标签简繁组合：特征/试证*可短写码；验证*禁止「验证码」以免误伤。"""
    from parsers.magnet import bare_infohash_structure_cue_labels

    h = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    labels = list(bare_infohash_structure_cue_labels())

    assert "特征编码" in labels
    assert "特征全码" in labels
    assert "特徵碼" in labels
    assert "特征码" in labels
    assert "试证全码" in labels
    assert "試證編碼" in labels
    assert "驗證編號" in labels
    assert "验证编码" in labels
    assert "验证全码" in labels
    assert "种子特码" in labels
    assert "种子编码" in labels
    assert "验证码" not in labels
    assert "驗證碼" not in labels

    for lab in labels:
        got = parse_magnet_text(f"【{lab}】：{h}")
        assert len(got) == 1 and got[0].infohash == h.upper(), lab


def test_verify_captcha_label_not_treated_as_infohash_cue():
    """「验证码」是站内验证码文案，不得把邻近 hex 扩成磁力。"""
    h = "cccccccccccccccccccccccccccccccccccccccc"
    for lab in ("验证码", "驗證碼", "验证碼", "驗證码"):
        assert parse_magnet_text(f"请输入【{lab}】：{h}") == []
        assert parse_magnet_text(f"{lab} {h}") == []


def test_parse_clipped_magnet_head_agnet():
    """防和谐砍首字母：agnet:?xt=urn:btih:…（tid 2506349）。"""
    h = "A888D42A29828F820CCD1F04B593B161EF953A92"
    raw = f"下载地址：\nagnet:?xt=urn:btih:{h}"
    assert "magnet:?xt=urn:btih:" in normalize_magnet_corpus(raw)
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(raw, "magnet")


def test_judge_imports_clipped_magnet_agnet():
    h = "A888D42A29828F820CCD1F04B593B161EF953A92"
    html = f"""
    <html><head><title>【自转】【磁力链接】掐字母测试</title></head>
    <body>
    <span id="thread_subject">【自转】【磁力链接】掐字母测试</span>
    <div id="postmessage_1">
      【影片名称】：掐字母磁力
      【下载地址】：
      <div class="blockcode"><div id="code_x"><ol>
        <li>agnet:?xt=urn:btih:{h}
      </ol></div></div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    links = parse_magnet_text(html)
    assert len(links) == 1 and links[0].infohash == h
    out = judge_thread_html(
        html,
        board_fid="142:697",
        list_title="【自转】【磁力链接】掐字母测试",
        preferred_link="magnet",
    )
    assert out.verdict == "import"
    assert out.link_kind == "magnet"


def test_parse_truncated_ed2k_scheme():
    """发帖掐掉 e：d2k://|file|… 应还原为 ed2k。"""
    from parsers.ed2k import normalize_ed2k_corpus, parse_ed2k_text

    raw = (
        "d2k://|file|www.98T.la@demo.mp4|2130880573|5EDD1B7979E9B5B98377D0E4B66624EA|/"
    )
    assert normalize_ed2k_corpus(raw).startswith("ed2k://")
    links = parse_ed2k_text(raw)
    assert len(links) == 1
    assert links[0].hash == "5EDD1B7979E9B5B98377D0E4B66624EA"
    assert links[0].link.startswith("ed2k://")
    assert has_target_link(raw, "ed2k")


def test_judge_imports_truncated_ed2k_scheme():
    html = """
    <html><head><title>【自转】【eD2k链接】掐字母测试</title></head>
    <body>
    <span id="thread_subject">【自转】【eD2k链接】掐字母测试</span>
    <div id="postmessage_1">
      <div class="blockcode"><div id="code_x"><ol>
        <li>d2k://|file|www.98T.la@demo.mp4|2130880573|5EDD1B7979E9B5B98377D0E4B66624EA|/
      </ol></div></div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    outcome = judge_thread_html(
        html,
        board_fid=95,
        list_title="【自转】【eD2k链接】掐字母测试",
        preferred_link="ed2k",
    )
    assert outcome.verdict == "import"
    assert outcome.parsed is not None
    assert outcome.parsed.ed2k_links
    assert outcome.parsed.ed2k_links[0].hash == "5EDD1B7979E9B5B98377D0E4B66624EA"


def test_judge_ed2k_board_imports_magnet_only():
    html = f"""
    <html><head><title>测试磁力资源贴</title></head>
    <body>
    <div id="postmessage_1">{MAGNET}</div>
    Powered by Discuz!
    </body></html>
    """
    # pad length so short-html / soft-shell gates do not fire
    html = html + ("<!-- pad -->" * 900)

    outcome = judge_thread_html(html, board_fid=95, list_title="测试磁力资源贴")
    assert outcome.verdict == "import"
    assert outcome.link_kind == "magnet"
    assert outcome.parsed is not None
    assert outcome.parsed.primary_link_kind == "magnet"
    assert outcome.parsed.assets


def test_judge_imports_fullwidth_colon_magnet():
    html = """
    <html><head><title>【磁力】全角冒号测试</title></head>
    <body>
    <span id="thread_subject">【磁力】全角冒号测试</span>
    <div id="postmessage_1">magnet：?xt=urn：btih：33C4355AE4E69DB5AAA568E825A552ED29FD75BB</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    outcome = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【磁力】全角冒号测试",
        preferred_link="ed2k",
    )
    assert outcome.verdict == "import"
    assert outcome.parsed is not None
    assert outcome.parsed.magnets


def test_parse_fully_spaced_magnet_scheme():
    """m a g n e t : ? xt = urn : btih : HASH"""
    h = "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    raw = f"m a g n e t : ? xt = urn : btih : {h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(raw, "magnet")


def test_parse_magnet_missing_question_mark():
    """magnet:xt=… / magnet://xt=…"""
    h = "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    for raw in (
        f"magnet:xt=urn:btih:{h}",
        f"magnet:/xt=urn:btih:{h}",
        f"magnet://xt=urn:btih:{h}",
    ):
        links = parse_magnet_text(raw)
        assert len(links) == 1 and links[0].infohash == h, raw


def test_parse_clipped_magnet_heads_extra():
    """magne / magent / mgnet 砍字母变体。"""
    h = "A888D42A29828F820CCD1F04B593B161EF953A92"
    for head in ("magne", "magent", "mgnet"):
        raw = f"{head}:?xt=urn:btih:{h}"
        links = parse_magnet_text(raw)
        assert len(links) == 1 and links[0].infohash == h, head


def test_parse_btih_space_before_hash():
    """magnet:?xt=urn:btih HASH（冒号被空格代替）"""
    h = "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    raw = f"magnet:?xt=urn:btih {h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h


def test_parse_magnet_entity_colon_and_zwsp():
    """&colon; / 零宽字符打断"""
    h = "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    raw = f"magnet&colon;?xt=urn&colon;btih&colon;{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    zw = f"mag\u200bnet:?xt=urn:btih:{h}"
    assert len(parse_magnet_text(zw)) == 1


def test_parse_ed2k_truncated_and_spaced_scheme():
    from parsers.ed2k import normalize_ed2k_corpus, parse_ed2k_text

    h = "ABCDEFABCDEFABCDEFABCDEFABCDEFAB"
    body = f"demo.mp4|10|{h}|/"
    for raw in (
        f"d2k://|file|{body}",
        f"e2k://|file|{body}",
        f"edk://|file|{body}",
        f"ed2://|file|{body}",
        f"e d 2 k : / / | file |{body}",
        f"ed2k:|file|{body}",
        f"ed2k:/|file|{body}",
    ):
        fixed = normalize_ed2k_corpus(raw)
        assert "ed2k://|file|" in fixed, raw
        links = parse_ed2k_text(raw)
        assert len(links) == 1 and links[0].hash == h, raw


def test_parse_ed2k_spaced_pipes_and_fullwidth():
    from parsers.ed2k import parse_ed2k_text

    h = "ABCDEFABCDEFABCDEFABCDEFABCDEFAB"
    raw = f"ed2k:// | file | demo.mp4 | 10 | {h} |/"
    links = parse_ed2k_text(raw)
    assert len(links) == 1
    assert links[0].hash == h
    fw = f"ed2k：／／｜file｜demo.mp4｜10｜{h}｜/"
    links2 = parse_ed2k_text(fw)
    assert len(links2) == 1
    assert links2[0].hash == h


def test_parse_ed2k_filename_keeps_fullwidth_pipe():
    """片名含全角｜时不得被 normalize 拆坏（色花堂转帖常见）。"""
    from parsers.ed2k import normalize_ed2k_corpus, parse_ed2k_text

    h = "B3353D2041F2C0411BEB90090E8A4CB2"
    raw = (
        "ed2k://|file|www.98T.la@FansOne 郑原创｜精华版｜梦幻剧情.mp4|"
        f"340422447|{h}|/"
    )
    assert "｜精华版｜" in normalize_ed2k_corpus(raw)
    links = parse_ed2k_text(raw)
    assert len(links) == 1
    assert links[0].hash == h
    assert "｜精华版｜" in links[0].filename


def test_parse_magnet_btih_link_aspx_hash():
    """magnet:?xt=urn:btih:link.aspx?hash=HEX（tid 1256892 jukujo）。"""
    h = "472B011E237DD9C8C80C02407AF91739225EFD09"
    raw = f"magnet:?xt=urn:btih:link.aspx?hash={h}"
    fixed = normalize_magnet_corpus(raw)
    assert f"magnet:?xt=urn:btih:{h}" in fixed
    assert "link.aspx?hash=" not in fixed.lower()
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(raw, "magnet")


def test_parse_magnet_scheme_split_from_xt_by_html_tags():
    """magnet:? 与 xt=urn:btih: 被 font/blockcode 拆开（tid 2012676）。"""
    h = "7647B28982C984F05F3AB20ADA170BD6A9487D52"
    raw = (
        f'<font color="#ff0000">magnet:?</font><br />'
        f'<div class="blockcode"><ol><li>xt=urn:btih:{h}'
        f"&amp;dn=demo.mp4</ol></div>"
    )
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(raw, "magnet")


def test_parse_magnet_btih_leading_slash():
    """magnet:?xt=urn:btih:/HASH（tid 700913）。"""
    h = "E283FFB0062623A275EF645162124F8FE7507042"
    raw = f"magnet:?xt=urn:btih:/{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h


def test_parse_magnet_urn_missing_btih():
    """magnet:?xt=urn:HASH 缺 btih:（tid 442964）。"""
    h = "8874953A5594EC85F00BDA4E3001045B362EFE3A"
    raw = f"【下载地址】：magnet:?xt=urn:{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h


def test_parse_magnet_clipped_to_net():
    """net:?xt=urn:btih:HASH（tid 582630）。"""
    h = "223b40a3ab682a9ad5f7f009eef7bf6c7818ebf4"
    raw = f"net:?xt=urn:btih:{h}&www.fulisoso.net-"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash.upper() == h.upper()


def test_parse_bare_hash_after_nbsp_feature_code():
    """特征码，&nbsp; HASH（tid 718959）。"""
    h = "ac1d5ce61d2cd2e5bcfaea54a832b4c4061c9e51"
    raw = f"特征码，&nbsp; &nbsp;{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash.upper() == h.upper()


def test_parse_bare_hash_spaced_feature_code_label():
    """【特 徵 碼 】字间插空（tid 1473899 破坏版）。"""
    h = "da783ddcb70e4e89e198a6b2a002276f458fd303"
    raw = f"【特 徵 碼 】：{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash.upper() == h.upper()
    assert has_target_link(raw, "magnet")


def test_parse_feature_label_interleaved_dot_and_sep_symbols():
    """标签字间点号/间隔号 + 标签后特殊分隔符仍认裸 hash。"""
    from parsers.content import extract_metadata

    h = "da783ddcb70e4e89e198a6b2a002276f458fd303"
    for raw in (
        f"【特·徵·碼】：{h}",
        f"【特.徵.碼】︰{h}",
        f"【驗 證 編 號】｜{h}",
        f"【特 徵 全 碼 】→{h}",
    ):
        links = parse_magnet_text(raw)
        assert len(links) == 1 and links[0].infohash.upper() == h.upper(), raw
        assert has_target_link(raw, "magnet"), raw
    meta = extract_metadata(f"【影 片 大 小】：4.39G\n【特 徵 碼 】：{h}")
    assert meta.get("影片大小") == "4.39G" or meta.get("資源大小") == "4.39G" or meta.get("资源大小") == "4.39G"
    assert any(k.replace(" ", "") in {"特徵碼", "特征码", "特徵码", "特征碼"} for k in meta)


def test_parse_magnet_dn_before_xt():
    """magnet:?dn=NAME&xt=urn:btih:HASH（JAVPLAYER tid 513815）。"""
    h = "034E3A2F3AC9B29E96C98D09A1D5953AB84DF884"
    raw = f"magnet:?dn=ABS-223_000&amp;xt=urn:btih:{h}"
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h
    assert has_target_link(raw, "magnet")


def test_parse_magnet_hash_split_by_br():
    """btih hash 被 <br> 拆成两段（tid 191451）。"""
    h = "B7FC49C33D009772E369670BEBB9CF1FFCC1DA72"
    raw = (
        "【下载地址】magnet:?xt=urn:btih:B7FC49C33D009772E369670BEBB9CF1<br />\n\n"
        "FFCC1DA72<br />"
    )
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == h


def test_judge_import_jukujo_link_aspx_and_split_magnet():
    """门控与 dual 对齐：两种残磁链应 import，勿「未解析到」。"""
    from workers.thread_outcome import judge_thread_html

    h1 = "472B011E237DD9C8C80C02407AF91739225EFD09"
    html1 = f"""
    <html><head><title>【磁力】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【磁力】示例</span>
    <div id="postmessage_1">
      【资源名称】：demo<br/>
      <div class="blockcode"><ol><li>magnet:?xt=urn:btih:link.aspx?hash={h1}</ol></div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html1 = html1 + ("x" * 15000)
    out1 = judge_thread_html(
        html1, board_fid="104", list_title="【磁力】示例", preferred_link="magnet"
    )
    assert out1.verdict == "import", out1.outcome

    h2 = "7647B28982C984F05F3AB20ADA170BD6A9487D52"
    html2 = f"""
    <html><head><title>【磁力鏈接】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【磁力鏈接】示例</span>
    <div id="postmessage_1">
      【影片名称】：demo<br/>
      <font color="#ff0000">magnet:?</font><br/>
      <div class="blockcode"><ol><li>xt=urn:btih:{h2}&amp;dn=demo.mp4</ol></div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html2 = html2 + ("x" * 15000)
    out2 = judge_thread_html(
        html2, board_fid="104", list_title="【磁力鏈接】示例", preferred_link="magnet"
    )
    assert out2.verdict == "import", out2.outcome
