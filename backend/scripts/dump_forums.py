import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.fetcher import Fetcher
from crawler.forum_index import parse_forum_index
from crawler.session import SessionManager


async def main():
    s = SessionManager()
    f = Fetcher(s)
    await s.bootstrap()
    html = await f.get_html("https://www.sehuatang.net/forum.php")
    sections = parse_forum_index(html)
    out = [{"fid": x.fid, "name": x.name, "parent": x.parent} for x in sections]
    out_path = ROOT / "data" / "forums.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in sections:
        if "转帖" in x.name or "网友" in x.name:
            print(x.fid, x.name, x.parent)


asyncio.run(main())
