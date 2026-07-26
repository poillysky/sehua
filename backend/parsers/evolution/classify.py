"""Title → bucket classification for parse-evolution workflow."""
from __future__ import annotations


def classify_title(title: str) -> str:
    t = title or ""
    low = t.lower()
    if "tj1221" in low or "▲tj" in t:
        if "欧美" in t or "歐美" in t:
            return "tj1221_欧美"
        if "马克" in t or "破壞" in t or "破坏" in t:
            return "tj1221_马克赛"
        if "FC2" in t.upper():
            return "tj1221_FC2"
        if "素人" in t:
            return "tj1221_素人"
        return "tj1221_其他"
    if "灣搭" in t or "湾搭" in t:
        if "中字" in t:
            return "湾搭_中字"
        if "素人" in t:
            return "湾搭_素人"
        return "湾搭_其他"
    if "欧美" in t or "歐美" in t:
        return "欧美合集"
    if "亚洲" in t or "亞洲" in t:
        return "亚洲合集"
    if "动漫" in t or "動漫" in t:
        return "动漫合集"
    if "国产" in t or "國產" in t or "自拍" in t:
        return "国产合集"
    if "FC2" in t.upper():
        return "FC2合集"
    if "有码" in t or "有碼" in t or "中字" in t:
        return "有码中字"
    if "无码" in t or "無碼" in t:
        return "无码合集"
    if "独家合集" in t:
        return "独家合集"
    if "合集" in t or "×" in t or "集合" in t:
        return "其他合集"
    return "单帖或其他"
