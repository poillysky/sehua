"""Cloudflare 邮箱保护误伤解压密码：应还原为明文。"""

from __future__ import annotations

from parsers.content import (
    decode_cf_email,
    extract_password,
    parse_thread_content,
    restore_cloudflare_emails,
)


def _encode_cf_email(plain: str, key: int = 0x5A) -> str:
    out = f"{key:02x}"
    for ch in plain.encode("utf-8"):
        out += f"{ch ^ key:02x}"
    return out


def test_decode_roundtrip_password_like():
    plain = "1998@www.98T.la"
    enc = _encode_cf_email(plain)
    assert decode_cf_email(enc) == plain


def test_restore_cf_anchor_in_html():
    plain = "1998@www.98T.la"
    enc = _encode_cf_email(plain)
    html = (
        f'【解压密码】：<a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
        f'data-cfemail="{enc}">[email&#160;protected]</a>'
        f'【文件大小】：1V/379M'
    )
    restored = restore_cloudflare_emails(html)
    assert plain in restored
    assert "email-protection" not in restored.lower() or plain in restored


def test_parse_thread_extract_password_not_placeholder():
    plain = "1998@www.98T.la"
    enc = _encode_cf_email(plain)
    html = f"""
    <html><head><title>测试帖</title></head><body>
    <span id="thread_subject">演示</span>
    <div id="postmessage_1">
      【资源类型】：视频<br/>
      【是否有码】：无码<br/>
      【有无第三方水印】：有<br/>
      【解压密码】：
      <a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="{enc}">
        [email&#160;protected]
      </a><br/>
      【文件大小】：1V/379M<br/>
      【时间长度】：12分钟
    </div>
    </body></html>
    """
    content = parse_thread_content(html, tid=3622331)
    assert content.extract_password == plain
    assert "[email" not in content.extract_password.lower()
    assert content.metadata.get("解压密码") == plain


def test_bogus_placeholder_rejected():
    assert extract_password("【解压密码】：[email protected]") == ""


def test_password_clipped_before_next_fields():
    blob = (
        "【解压密码】：1998@www.98T.la 【文件大小】： 5V/126M/1配额 "
        "【时间长度】：3分钟 【影片有无声音】：有 某房7月09日原版 ￥12 "
        "【剧情连拍截图/缩略图】 98 (4).png (677.68 KB, 下载次数: 0) 下载附件 "
        "百度网盘 ed2k://|file|x.zip|1|ABC|/ 复制代码 评分"
    )
    content = parse_thread_content(
        f"<html><body><div id='postmessage_1'>{blob}</div></body></html>",
        tid=1,
    )
    assert content.extract_password == "1998@www.98T.la"
    assert content.metadata.get("解压密码") == "1998@www.98T.la"
    assert "文件大小" not in (content.extract_password or "")
    assert content.metadata.get("文件大小", "").startswith("5V")


def test_description_only_allowlisted_labels():
    from parsers.links import parse_thread_dual

    html = """
    <html><body>
    <span id="thread_subject">演示标题</span>
    <div id="postmessage_1">
      【资源名称】：抖音超甜妹子 coco<br/>
      【资源类型】：视频<br/>
      【是否有码】：无码<br/>
      【有无第三方水印】：有<br/>
      【解压密码】：1998@www.98T.la<br/>
      【文件大小】：3V/542M<br/>
      【时间长度】：5分34<br/>
      【剧情连拍截图/缩略图】一堆附图<br/>
      沙发 发表于 前天 谢谢分享
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=1, board_fid=95)
    desc = parsed.description
    assert "【资源名称】" in desc
    assert "【资源类型】：视频" in desc
    assert "【是否有码】：无码" in desc
    assert "【有无第三方水印】：有" in desc
    assert "【解压密码】：1998@www.98T.la" in desc
    assert "【资源大小】：3V/542M" in desc
    assert "时间长度" not in desc
    assert "剧情连拍" not in desc
    assert "沙发" not in desc
    assert "谢谢分享" not in desc
    assert "种子期限" not in desc
    assert "下载工具" not in desc


def test_description_strips_attach_ui_and_replies():
    """一楼附件区 + 回复楼不得灌进【资源大小】等字段。"""
    from parsers.links import parse_thread_dual

    html = """
    <html><body>
    <span id="thread_subject">TD-21 大野まや 速水真保</span>
    <div id="postmessage_1">
      【资源名称】：TD-21 大野まや 速水真保<br/>
      【资源类型】：视频<br/>
      【是否有码】：无码<br/>
      【第三方水印】：无<br/>
      【资源大小】：2.6G/1V/1配额<br/>
      dvd1td21 (2).jpeg (103.3 KB, 下载次数: 0)
      下载附件 2026-03-22 05:21 上传
      ScreenShot_2026-03-13_085622_310.jpg (725.6 KB, 下载次数: 0)
      下载附件 2026-03-22 05:21 上传
      www.98T.la@TD-21.txt (105 Bytes, 下载次数: 263)
      点击文件名下载附件 阅读权限: 25
      评分 参与人数 18 评分 +30 收起 理由
    </div>
    <div id="post_2">
      <div id="postmessage_2">
        沙发 发表于 2026-03-22 09:08:37 | 只看该作者
        老片新看乐趣多 回复 使用道具 举报
        亚博美女赌场 推荐大發赌场
      </div>
    </div>
    Powered by Discuz! X3.4
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=3388894, board_fid=95)
    desc = parsed.description
    assert "【资源名称】：TD-21 大野まや 速水真保" in desc
    assert "【资源类型】：视频" in desc
    assert "【资源大小】：2.6G/1V/1配额" in desc
    assert "【是否有码】：无码" in desc
    assert "下载附件" not in desc
    assert "下载次数" not in desc
    assert "ScreenShot_" not in desc
    assert "沙发" not in desc
    assert "亚博" not in desc
    assert "Powered by" not in desc
    assert "只看该作者" not in desc


def test_description_enum_fields_not_swallow_replies_before_size():
    """字段顺序错乱/一楼边界失败时，资源类型等短字段不得吞回复与 ed2k。"""
    from parsers.links import parse_thread_dual

    html = """
    <html><body>
    <span id="thread_subject">【整理】【115ED2K】倪海厦中医养生视频【70.6G/1169V//7配额】</span>
    <div id="postmessage_3368244">
      【资源名称】：倪海厦中医养生视频<br/>
      【资源类型】：视频<br/>
      有人说这是骗子别信 回复 支持 使用道具 举报<br/>
      发表于 2026-03-12 18:56:14 | 只看该作者<br/>
      ed2k://|file|www.98T.la@本草.rar|1|05C8CF408C1E53AFE6E848387A2CF4BB|/<br/>
      Powered by Discuz! X3.4<br/>
      【资源大小】：70.6G/1169V//7配额<br/>
      【是否有码】：有码<br/>
      【有无第三方水印】：有水印<br/>
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=3368244, board_fid=95)
    desc = parsed.description
    assert "【资源名称】：倪海厦中医养生视频" in desc
    assert "【资源类型】：视频" in desc
    assert "【资源大小】：70.6G/1169V//7配额" in desc
    assert "【是否有码】：有码" in desc
    assert "【有无第三方水印】：有水印" in desc
    assert "骗子" not in desc
    assert "发表于" not in desc
    assert "ed2k://" not in desc
    assert "Powered by" not in desc
    assert "只看该作者" not in desc


def test_file_size_strips_promo_blurb_after_quota():
    """thread-3363393：文件大小后跟博主导语，不得并进资源大小。"""
    from parsers.links import parse_thread_dual

    html = """
    <html><body>
    <span id="thread_subject">【自转】【百度/115eD2k】韩国顶级健身肥臀女神【Yuyuhwa】付费合集【82V+173P/6.7G/1配额】</span>
    <div id="postmessage_3363393">
      【资源名称】：【自转】【百度/115eD2k】韩国顶级健身肥臀女神【Yuyuhwa】付费合集【82V+173P/6.7G/1配额】
      【资源类型】：视频+图片 【是否有码】：无码 【有无第三方水印】： 有
      【解压密码】：1998@www.98T.la
      【文件大小】： 82V+173P/6.7G/1配额 某房3月7日￥26资源 韩国顶级健身肥臀巨乳Yuyuhwa 顶级巨乳 肥臀 完美颜值
      【剧情连拍截图】
      www.98T.la@ (2).png (559.43 KB, 下载次数: 0)
      下载附件
      【资源预览】
      www.98T.la@ (5).png (875.18 KB, 下载次数: 0)
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=3363393, board_fid=95)
    desc = parsed.description
    assert "【资源类型】：视频+图片" in desc
    assert "【资源大小】：82V+173P/6.7G/1配额" in desc
    assert "某房" not in desc
    assert "完美颜值" not in desc
    assert "下载附件" not in desc
    assert "【资源名称】：" in desc
    assert "Yuyuhwa" in desc
    assert "【解压密码】：1998@www.98T.la" in desc


def test_bt_board_keeps_film_labels():
    from parsers.links import parse_thread_dual

    html = """
    <html><body>
    <span id="thread_subject">BT演示</span>
    <div id="postmessage_1">
      【影片名称】：某某影片<br/>
      【出演女优】：AAA<br/>
      【影片容量】：4.2GB<br/>
      【是否有码】：有码<br/>
      【种子期限】：30天<br/>
      【下载工具】：xxx<br/>
      【影片预览】：一堆图
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=2, board_fid=2)
    desc = parsed.description
    assert "【影片名称】：某某影片" in desc
    assert "【出演女优】：AAA" in desc
    assert "【影片容量】：4.2GB" in desc
    assert "【是否有码】：有码" in desc
    assert "种子期限" not in desc
    assert "下载工具" not in desc
    assert "影片预览" not in desc


def test_password_shi_copula_not_captured():
    """「解压密码是www.98T.la@」不应把「是」当成密码。"""
    assert extract_password("解压密码是www.98T.la@") == "www.98T.la@"
    assert extract_password("解压密码是 www.98T.la@") == "www.98T.la@"
    assert extract_password("提取密码为www.98T.la@") == "www.98T.la@"
    text = (
        "解压密码是www.98T.la@，需要把后面《删除》这俩字删掉\n"
        "第一层为单个压缩包，密码www.98T.la@\n"
        "【资源名称】：演示"
    )
    assert extract_password(text) == "www.98T.la@"
    content = parse_thread_content(
        f"<html><body><div id='postmessage_1'>{text}</div></body></html>",
        tid=9,
    )
    assert content.extract_password == "www.98T.la@"
