import re
from pathlib import Path

html = Path("data/last_list.html").read_text(encoding="utf-8")
title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
print("TITLE:", re.sub(r"\s+", " ", title.group(1)).strip() if title else None)
print("len", len(html))
for pat in ["threadlist", "normalthread", "stickthread", "emptyswitch", "forumdisplay"]:
    print(pat, html.lower().count(pat.lower()))
print("国产", "国产" in html, "转帖", "转帖" in html, "综合", "综合讨论" in html)
print("投诉", "投诉" in html)
m = re.search(r'id="threadlist"[\s\S]{0,600}', html, re.I)
print("threadlist:", (m.group(0)[:500] if m else "NONE"))
# links near top
for m in re.finditer(r'href="([^"]*thread-\d+-1-1\.html)"[^>]*>([^<]{0,60})', html):
    print("link", m.group(1), m.group(2).strip()[:40])
    break
# body class / #ct
ct = re.search(r'id="ct"[^>]*>([\s\S]{0,300})', html, re.I)
print("ct:", (ct.group(0)[:250] if ct else "NONE"))
