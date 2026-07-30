# -*- coding: utf-8 -*-
"""帖标题以列表扫描为准，不用帖内标题覆盖。"""

from parsers.content import extract_title
from parsers.thread_gates import (
    coalesce_thread_title,
    prefer_fuller_title,
    title_looks_list_truncated,
)


def test_title_looks_list_truncated():
    assert title_looks_list_truncated("合集标题被截断...")
    assert title_looks_list_truncated("合集标题被截断…")
    assert title_looks_list_truncated("米苏推荐…高颜值大学...【17.2V")
    assert title_looks_list_truncated("内容写到一半【")
    assert not title_looks_list_truncated("对妻子说到嘴边…竟然让婆婆怀孕了。完整句")
    assert not title_looks_list_truncated("正常完整标题【1V/2G】")


def test_coalesce_prefers_list_over_fuller_thread():
    """列表截断也不用帖内完整标题覆盖——避免正文/subject 污染。"""
    list_t = "FC2PPV-4523370-ホ●トの彼氏と別れて3ヵ月…普段オナニーしない清楚なお姉さん。売●を支払"
    list_cut = list_t + "..."
    thread_t = (
        "FC2PPV-4523370-ホ●トの彼氏と別れて3ヵ月…普段オナニーしない清楚なお姉さん。"
        "売●を支払うためにオジサンと生ハメセックス。膣奥めがけて即射中出し！"
    )
    assert coalesce_thread_title(list_cut, thread_t) == list_cut
    assert coalesce_thread_title(list_cut, "提示信息", thread_t) == list_cut


def test_coalesce_access_denied_keeps_list_when_page_is_tip():
    list_title = "【自转】【115eD2k】无权帖列表标题【1V】"
    assert coalesce_thread_title(list_title, "提示信息") == list_title
    assert coalesce_thread_title("提示信息", list_title) == list_title


def test_coalesce_list_first_wins_even_if_shorter():
    short = "【整理】【115eD2k】米苏推荐分享自己收藏的反差泄密小姐姐三，精选珍藏...【17.2V"
    full = (
        "【整理】【115eD2k】米苏推荐分享自己收藏的反差泄密小姐姐三，精选珍藏多位高颜值"
        "小姐姐自收集泄密【17.2GB/476V】"
    )
    # 列表放第一位 → 保留列表（并补未闭合】）
    got = coalesce_thread_title(short, full)
    assert got.startswith("【整理】【115eD2k】米苏推荐")
    assert "多位高颜值" not in got
    assert got.endswith("】")


def test_prefer_fuller_title_no_longer_expands_from_body():
    subj = "真实良家偷拍，【推油少年】，女大学生..."
    body = "真实良家偷拍，【推油少年】，女大学生，漂亮露脸，粉嫩美乳，第一次尝试异性按摩就被操"
    assert prefer_fuller_title(subj, body) == subj


def test_extract_title_does_not_expand_from_body():
    """截断 subject 也不用正文名称改写标题——页面显示什么就存什么。"""
    html = """
    <span id="thread_subject">米苏推荐分享自己收藏的反差泄密小姐姐三，精选珍藏...【17.2V</span>
    <div class="t_f">
    【资源名称】：米苏推荐分享自己收藏的反差泄密小姐姐三，精选珍藏多位高颜值小姐姐自收集泄密
    【资源大小】：17.2GB
    </div>
    """
    t = extract_title(html)
    assert t.startswith("米苏推荐")
    assert "...【17.2V" in t or t.endswith("【17.2V】") or t.endswith("【17.2V")
    assert "多位高颜值" not in t
