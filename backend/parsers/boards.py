"""Board / subcategory crawl-unit registry.

爬取单位为「板块-分类」（fid:typeid），因 Discuz 列表最多约 2000 页，
分类越细可覆盖越多历史帖。无分类的板仍用整板 key=fid。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PrimaryLink = Literal["magnet", "ed2k", "both"]

# 版务类不入默认白名单
_BANWU_TYPEIDS = frozenset({"662", "708", "707"})

DISCUZ_BOARD_FID = 95
# 兼容旧常量：综合讨论区 · 情色分享
DISCUZ_SHARE_TYPEID = "716"


@dataclass(frozen=True, slots=True)
class BoardPolicy:
    """一条可勾选的爬取单位（板块 或 板块-分类）。"""

    key: str
    fid: int
    name: str
    category: str
    primary_link: PrimaryLink = "magnet"
    hot: bool = False
    priority: int = 50
    min_thread_age_days: int = 0
    list_typeid: str | None = None
    board_name: str = ""
    type_name: str = ""
    enabled: bool = True

    @property
    def display_name(self) -> str:
        return self.name


def board_unit_key(fid: int | str, typeid: str | int | None = None) -> str:
    fid_s = str(fid).strip()
    tid = str(typeid).strip() if typeid is not None and str(typeid).strip() else ""
    return f"{fid_s}:{tid}" if tid else fid_s


def parse_board_key(key: str | int | None) -> tuple[int, str | None]:
    """解析爬取单位 key → (fid, typeid|None)。纯数字视为整板。"""
    raw = str(key or "").strip()
    if not raw:
        return 0, None
    if ":" in raw:
        left, right = raw.split(":", 1)
        fid = int(left) if left.isdigit() else 0
        tid = right.strip() or None
        return fid, tid
    if raw.isdigit():
        return int(raw), None
    return 0, None


def _unit(
    fid: int,
    board_name: str,
    category: str,
    primary_link: PrimaryLink,
    *,
    typeid: str | None = None,
    type_name: str = "",
    hot: bool = False,
    priority: int = 50,
    min_thread_age_days: int = 0,
    enabled: bool = True,
) -> BoardPolicy:
    key = board_unit_key(fid, typeid)
    if typeid and type_name:
        name = f"{board_name} · {type_name}"
    else:
        name = board_name
    return BoardPolicy(
        key=key,
        fid=fid,
        name=name,
        category=category,
        primary_link=primary_link,
        hot=hot,
        priority=priority,
        min_thread_age_days=min_thread_age_days,
        list_typeid=str(typeid) if typeid else None,
        board_name=board_name,
        type_name=type_name or "",
        enabled=enabled,
    )


_DISCUZ = "综合讨论区"
_BT = "原创BT电影"

# 综合讨论区仅爬取情色分享（与线程判定 typeid=716 一致）
_TYPES_95: list[tuple[str, str]] = [
    ("716", "情色分享"),
]

_TYPES_141: list[tuple[str, str]] = [
    ("689", "国产合集"),
    ("690", "欧美合集"),
    ("691", "日本合集"),
    ("844", "合集推荐"),
    ("692", "破解"),
    ("705", "增强"),
    ("867", "换脸"),
    ("866", "自压"),
    ("879", "主播录播"),
    ("695", "套图"),
    ("694", "蓝光原盘"),
    ("693", "二次元"),
    ("696", "其它"),
    ("708", "版务"),
]

_TYPES_142: list[tuple[str, str]] = [
    ("697", "国产自拍"),
    ("698", "直播视频"),
    ("699", "亚洲无码"),
    ("700", "亚洲有码"),
    ("701", "偷拍視頻"),
    ("702", "动漫/二次元"),
    ("703", "欧美风情"),
    ("704", "其他資源"),
    ("706", "合集资源"),
    ("707", "版务管理"),
]

_TYPES_2: list[tuple[str, str]] = [
    ("684", "国产无码"),
    ("685", "主播录制"),
    ("686", "360水滴"),
    ("687", "厕所偷拍"),
]

_TYPES_36: list[tuple[str, str]] = [
    ("368", "FC2PPV"),
    ("369", "HEYZO"),
    ("370", "加勒比系列"),
    ("371", "一本道系列"),
    ("372", "10musume"),
    ("373", "女体のしんぴ"),
    ("374", "pacoma"),
    ("375", "heyppv"),
    ("379", "店長推薦"),
    ("449", "东京热"),
    ("523", "熟女俱樂部"),
    ("537", "xxx-av"),
    ("551", "人妻斬り"),
    ("552", "エッチな0930"),
    ("553", "エッチな4610"),
    ("583", "本生素人TV"),
    ("586", "sm-miracle"),
    ("587", "roselip-fetish"),
    ("589", "legsjapan"),
    ("590", "uralesbian"),
    ("591", "fellatiojapan"),
    ("618", "spermmania"),
    ("619", "handjobjapan"),
    ("631", "urabukkake"),
    ("654", "无码流出"),
    ("660", "金髪天國"),
    ("671", "加勒比PPV"),
    ("672", "无码破解"),
    ("683", "レズのしんぴ"),
    ("723", "japornxxx"),
    ("724", "盗窃系列"),
    ("822", "cospuri"),
]

_TYPES_103: list[tuple[str, str]] = [
    ("480", "有码高清"),
    ("481", "无码高清"),
]

_TYPES_151: list[tuple[str, str]] = [
    ("823", "无码"),
    ("824", "有码"),
]

_TYPES_39: list[tuple[str, str]] = [
    ("404", "无码"),
    ("405", "有码"),
]

# 三级写真 / 素人：分类极多，仍按子版拆开以突破 2000 页
_TYPES_107: list[tuple[str, str]] = [
    ("592", "日本写真"),
    ("593", "韩国三级"),
    ("594", "日本三级"),
    ("595", "美国三级"),
    ("596", "香港三级"),
    ("597", "国产三级"),
    ("598", "法国三级"),
    ("599", "美国四级"),
    ("600", "国产四级"),
    ("601", "英国四级"),
    ("602", "英国三级"),
    ("603", "台湾四级"),
    ("604", "泰国三级"),
    ("605", "法国四级"),
    ("606", "加拿大三级"),
    ("607", "意大利三级"),
    ("608", "荷兰三级"),
    ("609", "台湾三级"),
    ("610", "挪威三级"),
    ("611", "瑞士三级"),
    ("612", "瑞士四级"),
    ("613", "香港四级"),
    ("614", "阿根廷三级"),
    ("615", "泰国四级"),
    ("616", "波兰三级"),
    ("617", "国产写真"),
    ("620", "西班牙三级"),
    ("621", "墨西哥三级"),
    ("622", "俄罗斯三级"),
    ("623", "美国写真"),
    ("624", "德国三级"),
    ("625", "丹麦三级"),
    ("628", "克罗地亚三级"),
    ("629", "巴西三级"),
    ("630", "意大利四级"),
    ("633", "德国四级"),
    ("634", "瑞典四级"),
    ("645", "丹麦四级"),
    ("646", "荷兰写真"),
    ("650", "比利时四级"),
    ("655", "澳大利亚三级"),
    ("656", "印度三级"),
    ("657", "菲律宾三级"),
    ("658", "新加坡写真"),
    ("659", "韩国写真"),
    ("667", "法国写真"),
    ("668", "英国写真"),
    ("669", "俄罗斯写真"),
    ("670", "智利三级"),
]

_TYPES_104: list[tuple[str, str]] = [
    ("726", "SIRO"),
    ("727", "259LUXU"),
    ("728", "300MIUM"),
    ("729", "332NAMA"),
    ("730", "326EVA"),
    ("731", "328HMDN"),
    ("533", "G-area"),
    ("534", "Mywife"),
    ("535", "S-cute"),
    ("536", "FC2"),
    ("557", "himemix"),
    ("563", "getchu"),
    ("588", "siro-hame"),
    ("626", "r-file"),
    ("627", "giga-web"),
    ("632", "knights-visual"),
    ("725", "230OREX"),
    ("807", "336KNB"),
    ("808", "200GANA"),
    ("809", "300MAAN"),
    ("810", "300NTK"),
    ("811", "390JAC"),
    ("812", "326SCP"),
    ("813", "其他系列"),
]


def _expand(
    fid: int,
    board_name: str,
    category: str,
    primary_link: PrimaryLink,
    types: list[tuple[str, str]],
    *,
    base_priority: int,
    hot: bool = False,
    min_thread_age_days: int = 0,
) -> list[BoardPolicy]:
    out: list[BoardPolicy] = []
    for i, (typeid, type_name) in enumerate(types):
        banwu = typeid in _BANWU_TYPEIDS or "版务" in type_name
        out.append(
            _unit(
                fid,
                board_name,
                category,
                primary_link,
                typeid=typeid,
                type_name=type_name,
                hot=hot and i == 0,
                priority=base_priority * 100 + i,
                min_thread_age_days=min_thread_age_days,
                enabled=not banwu,
            )
        )
    return out


def _build_policies() -> dict[str, BoardPolicy]:
    units: list[BoardPolicy] = []
    units += _expand(95, "综合讨论区", _DISCUZ, "ed2k", _TYPES_95, base_priority=0)
    units += _expand(
        141, "网友原创区", _DISCUZ, "ed2k", _TYPES_141,
        base_priority=1, hot=True, min_thread_age_days=3,
    )
    units += _expand(142, "转帖交流区", _DISCUZ, "magnet", _TYPES_142, base_priority=2)
    units += _expand(2, "国产原创", _BT, "magnet", _TYPES_2, base_priority=10, hot=True)
    units += _expand(36, "亚洲无码原创", _BT, "magnet", _TYPES_36, base_priority=11, hot=True)
    # 无分类：整板
    units.append(_unit(37, "亚洲有码原创", _BT, "magnet", priority=1200))
    units += _expand(103, "高清中文字幕", _BT, "magnet", _TYPES_103, base_priority=13, hot=True)
    units += _expand(107, "三级写真", _BT, "magnet", _TYPES_107, base_priority=14)
    units.append(_unit(160, "VR视频区", _BT, "magnet", priority=1500))
    units += _expand(104, "素人有码系列", _BT, "magnet", _TYPES_104, base_priority=16)
    units.append(_unit(38, "欧美无码", _BT, "magnet", priority=1700))
    units += _expand(151, "4K原版", _BT, "magnet", _TYPES_151, base_priority=18)
    units.append(_unit(152, "韩国主播", _BT, "magnet", hot=True, priority=1900))
    units += _expand(39, "动漫原创", _BT, "magnet", _TYPES_39, base_priority=20)

    return {u.key: u for u in units}


BOARD_POLICIES: dict[str, BoardPolicy] = _build_policies()

# 旧代码 / 跳过板
SKIP_FIDS: frozenset[int] = frozenset({148})

# fid 级默认（描述解析、线程判定用；无 list_typeid 过滤）
_FID_DEFAULTS: dict[int, BoardPolicy] = {}
for _u in BOARD_POLICIES.values():
    if _u.fid not in _FID_DEFAULTS:
        _FID_DEFAULTS[_u.fid] = BoardPolicy(
            key=str(_u.fid),
            fid=_u.fid,
            name=_u.board_name or _u.name,
            category=_u.category,
            primary_link=_u.primary_link,
            hot=_u.hot,
            priority=_u.priority,
            min_thread_age_days=_u.min_thread_age_days,
            list_typeid=None,
            board_name=_u.board_name or _u.name,
            type_name="",
            enabled=True,
        )


def default_board_order() -> list[str]:
    """默认启用顺序：全部非版务子版。"""
    return [
        u.key
        for u in sorted(BOARD_POLICIES.values(), key=lambda x: x.priority)
        if u.enabled
    ]


def all_board_keys() -> set[str]:
    return set(BOARD_POLICIES.keys())


def expand_legacy_board_keys(keys: list[str] | None) -> list[str]:
    """把旧版纯 fid（如 \"95\"）展开为该板全部启用子版 key。"""
    if not keys:
        return []
    order = default_board_order()
    order_set = set(order)
    by_fid: dict[int, list[str]] = {}
    for key in order:
        fid, _ = parse_board_key(key)
        by_fid.setdefault(fid, []).append(key)

    out: list[str] = []
    seen: set[str] = set()
    for raw in keys:
        k = str(raw).strip()
        if not k:
            continue
        if k in BOARD_POLICIES:
            if k in order_set and k not in seen:
                out.append(k)
                seen.add(k)
            continue
        # 纯 fid → 展开
        if k.isdigit():
            for uk in by_fid.get(int(k), []):
                if uk not in seen:
                    out.append(uk)
                    seen.add(uk)
    return out


def board_display_name(pol: BoardPolicy) -> str:
    """资源/队列展示名：主板块 · 子分类。"""
    return (pol.name or pol.board_name or "").strip()


def queue_board_keys(unit_key: str | int) -> list[str]:
    """当前子版 key；附带旧纯 fid，便于消化历史入队。"""
    key = str(unit_key).strip()
    out: list[str] = []
    if key:
        out.append(key)
    fid, _ = parse_board_key(key)
    if fid:
        bare = str(fid)
        if bare not in out:
            out.append(bare)
    return out


def enabled_queue_board_keys(enabled_fids: list[str] | tuple[str, ...] | None) -> list[str]:
    """启用队列全部子版的待抓统计 key（去重，含旧纯 fid）。"""
    out: list[str] = []
    seen: set[str] = set()
    for efid in enabled_fids or []:
        for k in queue_board_keys(efid):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def get_board_policy(fid_or_key: int | str) -> BoardPolicy:
    """按爬取单位 key 或纯 fid 取策略。

    - \"95:716\" → 子版策略（含 list_typeid）
    - 95 / \"95\" → fid 级默认（无 list_typeid，供帖内判定/描述）
    """
    key = str(fid_or_key).strip()
    if key in BOARD_POLICIES:
        return BOARD_POLICIES[key]
    fid, tid = parse_board_key(key)
    if tid:
        # 未知子版：仍返回带 typeid 的临时策略
        base = _FID_DEFAULTS.get(fid)
        if base:
            return _unit(
                fid,
                base.board_name or base.name,
                base.category,
                base.primary_link,
                typeid=tid,
                type_name=tid,
                priority=base.priority,
                min_thread_age_days=base.min_thread_age_days,
            )
    if fid in _FID_DEFAULTS:
        return _FID_DEFAULTS[fid]
    return BoardPolicy(key=key or str(fid), fid=fid or 0, name=f"fid-{fid}", category="其他")


def get_board_fid(fid_or_key: int | str) -> int:
    fid, _ = parse_board_key(fid_or_key)
    if fid:
        return fid
    pol = get_board_policy(fid_or_key)
    return pol.fid


def list_enabled_boards() -> list[BoardPolicy]:
    return sorted(
        [b for b in BOARD_POLICIES.values() if b.enabled],
        key=lambda x: x.priority,
    )
