import re
from pathlib import Path

html = Path("data/list_2_heat.html").read_text(encoding="utf-8")
print("normalthread", len(re.findall(r'id="normalthread_(\d+)"', html)))
print("stickthread", len(re.findall(r'id="stickthread_(\d+)"', html)))
m = re.search(r'id="normalthread_(\d+)"([\s\S]{0,1500})', html)
if m:
    print("first normal tid", m.group(1))
    chunk = m.group(2)
    print("chunk hrefs:")
    for h in re.findall(r'href="([^"]+)"', chunk)[:12]:
        print(" ", h)
    print("text", re.sub(r"<[^>]+>", " ", chunk)[:180])
print("viewthread", len(re.findall(r"viewthread", html)))
print("tid=", len(re.findall(r"tid=\d+", html)))
print("thread-", len(re.findall(r"thread-\d+", html)))
# onclick / data
print("onclick thread", len(re.findall(r"thread-\d+", html)))
print("forum.php?mod=viewthread", len(re.findall(r"forum\.php\?mod=viewthread", html)))
