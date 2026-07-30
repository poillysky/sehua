"""Probe preview_images CDN URLs; rewrite 404 tu.* hosts to a working mirror."""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.resource_db import connect_resource

MIRRORS = ("tu.ewrewej.la", "tu.ymawv.la", "tu.ldkms.la")
UA = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.sehuatang.net/",
}


def head_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            return 200 <= int(r.status) < 300
    except Exception:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=12) as r:
                ct = (r.headers.get("content-type") or "").lower()
                return 200 <= int(r.status) < 300 and ct.startswith("image/")
        except Exception:
            return False


def with_host(url: str, host: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(netloc=host))


def repair_url(url: str) -> str:
    try:
        p = urlparse(url)
    except Exception:
        return url
    host = (p.hostname or "").lower()
    if host not in MIRRORS:
        return url
    if "/tupian/forum/" not in (p.path or ""):
        return url
    if head_ok(url):
        return url
    for h in MIRRORS:
        if h == host:
            continue
        alt = with_host(url, h)
        if head_ok(alt):
            return alt
    return url


def main() -> None:
    c = connect_resource()
    cur = c.cursor()
    cur.execute(
        "SELECT id, preview_images FROM resource_sources "
        "WHERE preview_images IS NOT NULL AND cardinality(preview_images) > 0"
    )
    changed = 0
    for rid, prev in cur.fetchall():
        imgs = list(prev or [])
        new = [repair_url(u) for u in imgs]
        if new == imgs:
            continue
        print(f"id={rid}")
        for a, b in zip(imgs, new):
            if a != b:
                print(f"  {a}\n  -> {b}")
        cur.execute(
            "UPDATE resource_sources SET preview_images=%s WHERE id=%s",
            (new, rid),
        )
        changed += 1
    c.commit()
    c.close()
    print(f"done rows_changed={changed}")


if __name__ == "__main__":
    main()
