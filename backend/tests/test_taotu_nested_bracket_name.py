# -*- coding: utf-8 -*-
"""套图名称以【装饰】开头不得被截成空（tid=27268283）。"""

from __future__ import annotations

from parsers.content import _subresource_title_value


def test_taotu_name_keeps_leading_decorative_brackets():
    scope = (
        "【套圖名稱】: 【重磅核弹】阿曼达付费VIP，九位绝品女神福利<br/>"
        "【套圖數量】: 58P+54V<br/>"
        "【套圖名稱】: 下一条"
    )
    import re

    m = re.search(r"【套圖名稱】", scope)
    assert m
    t_end = m.end()
    next_start = scope.index("【套圖名稱】", t_end)
    name = _subresource_title_value(
        scope, t_end, next_start, label_start=m.start(), thread_title="合集标题"
    )
    assert "阿曼达" in name
    assert name.startswith("【重磅核弹】")
    assert name != ""


def test_taotu_name_still_cuts_trailing_marketing_bracket():
    scope = (
        "【套圖名稱】: 推特超美反差女神【限时促销】广告文案<br/>"
        "【套圖名稱】: 下一条"
    )
    import re

    m = re.search(r"【套圖名稱】", scope)
    assert m
    t_end = m.end()
    next_start = scope.index("【套圖名稱】", t_end)
    name = _subresource_title_value(
        scope, t_end, next_start, label_start=m.start(), thread_title=""
    )
    assert name == "推特超美反差女神"
