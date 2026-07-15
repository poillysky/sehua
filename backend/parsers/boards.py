"""Board policy registry — aligned with ed2k sehuatang whitelist.

爬取规则（与 ed2k 一致）：
- 原创BT电影：除 fid 148 外全部爬取（磁力为主）
- 综合讨论区：fid=95 仅 typeid=716；141 ED2K（仅爬满 3 天帖）；142 转帖交流区磁力
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PrimaryLink = Literal["magnet", "ed2k", "both"]

# fid=95 综合讨论区：仅爬「情色分享」主题分类
DISCUZ_BOARD_FID = 95
DISCUZ_SHARE_TYPEID = "716"


@dataclass(frozen=True, slots=True)
class BoardPolicy:
    fid: int
    name: str
    category: str
    primary_link: PrimaryLink = "magnet"
    hot: bool = False
    priority: int = 50
    min_thread_age_days: int = 0
    list_typeid: str | None = None
    enabled: bool = True


_BT = "原创BT电影"
_DISCUZ = "综合讨论区"

# Whitelist — order by priority (lower = higher crawl priority in board_order default)
BOARD_POLICIES: dict[int, BoardPolicy] = {
    95: BoardPolicy(
        95, "综合讨论区", _DISCUZ, "ed2k",
        hot=False, priority=0, list_typeid=DISCUZ_SHARE_TYPEID,
    ),
    141: BoardPolicy(
        141, "网友原创区", _DISCUZ, "ed2k",
        hot=True, priority=1, min_thread_age_days=3,
    ),
    142: BoardPolicy(
        142, "转帖交流区", _DISCUZ, "magnet",
        hot=False, priority=2,
    ),
    2: BoardPolicy(2, "国产原创", _BT, "magnet", hot=True, priority=10),
    36: BoardPolicy(36, "亚洲无码原创", _BT, "magnet", hot=True, priority=11),
    37: BoardPolicy(37, "亚洲有码原创", _BT, "magnet", hot=False, priority=12),
    103: BoardPolicy(103, "高清中文字幕", _BT, "magnet", hot=True, priority=13),
    107: BoardPolicy(107, "三级写真", _BT, "magnet", hot=False, priority=14),
    160: BoardPolicy(160, "VR视频区", _BT, "magnet", hot=False, priority=15),
    104: BoardPolicy(104, "素人有码系列", _BT, "magnet", hot=False, priority=16),
    38: BoardPolicy(38, "欧美无码", _BT, "magnet", hot=False, priority=17),
    151: BoardPolicy(151, "4K原版", _BT, "magnet", hot=False, priority=18),
    152: BoardPolicy(152, "韩国主播", _BT, "magnet", hot=True, priority=19),
    39: BoardPolicy(39, "动漫原创", _BT, "magnet", hot=False, priority=20),
}

SKIP_FIDS: frozenset[int] = frozenset({148})


def default_board_order() -> list[str]:
    return [str(b.fid) for b in sorted(BOARD_POLICIES.values(), key=lambda x: x.priority)]


def get_board_policy(fid: int) -> BoardPolicy:
    return BOARD_POLICIES.get(fid, BoardPolicy(fid, f"fid-{fid}", "其他"))


def list_enabled_boards() -> list[BoardPolicy]:
    return sorted(
        [b for b in BOARD_POLICIES.values() if b.enabled],
        key=lambda x: x.priority,
    )
