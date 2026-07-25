"""Forum site registry."""

from __future__ import annotations

from crawler.sites.base import ForumSiteAdapter
from crawler.sites.forum_2048 import ADAPTER as ADAPTER_2048
from crawler.sites.sehuatang import ADAPTER as ADAPTER_SEHUATANG

_REGISTRY: dict[str, ForumSiteAdapter] = {
    "sehuatang": ADAPTER_SEHUATANG,
    "2048": ADAPTER_2048,
}


def get_site_adapter(forum_id: str | None = None) -> ForumSiteAdapter:
    fid = (forum_id or "sehuatang").strip() or "sehuatang"
    return _REGISTRY.get(fid) or ADAPTER_SEHUATANG


def is_phpwind(forum_id: str | None = None) -> bool:
    return get_site_adapter(forum_id).engine == "phpwind"
