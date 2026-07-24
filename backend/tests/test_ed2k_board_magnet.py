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
    """实录标签简繁组合：特征*可短写码；验证*禁止「验证码」以免误伤。"""
    from parsers.magnet import (
        _BARE_HASH_BACK1_FEATURE,
        _BARE_HASH_BACK2,
        _BARE_HASH_FRONT_FEATURE,
        _BARE_HASH_FRONT_VERIFY,
    )

    h = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    labels: list[str] = []
    for front in _BARE_HASH_FRONT_FEATURE:
        for back in _BARE_HASH_BACK2:
            labels.append(front + back)
        for back in _BARE_HASH_BACK1_FEATURE:
            labels.append(front + back)
    for front in _BARE_HASH_FRONT_VERIFY:
        for back in _BARE_HASH_BACK2:
            labels.append(front + back)
    for seed in ("种", "種"):
        for code in ("码", "碼"):
            labels.append(f"{seed}子特{code}")

    assert "特征编码" in labels
    assert "特徵碼" in labels
    assert "特征码" in labels
    assert "驗證編號" in labels
    assert "验证编码" in labels
    assert "种子特码" in labels
    assert "验证码" not in labels
    assert "驗證碼" not in labels

    expected = (
        len(_BARE_HASH_FRONT_FEATURE) * (len(_BARE_HASH_BACK2) + len(_BARE_HASH_BACK1_FEATURE))
        + len(_BARE_HASH_FRONT_VERIFY) * len(_BARE_HASH_BACK2)
        + 4
    )
    assert len(labels) == expected

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
