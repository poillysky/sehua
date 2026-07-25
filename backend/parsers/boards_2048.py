"""2048（人人为我 / PHPWind）板块白名单。

列表：thread.php?fid=N ；帖子：read.php?tid=N。
主链策略：优先磁力，无磁力再 ED2K（primary_link=magnet）。
"""

from __future__ import annotations

from parsers.boards import BoardPolicy, _unit

_CAT_NEW = "新片合集"
_CAT_AREA = "分区资源"
_CAT_BT = "BT磁力"


def _build_policies_2048() -> dict[str, BoardPolicy]:
    # 用户白名单：子版直爬；主链优先磁力再 ed2k
    units: list[BoardPolicy] = [
        _unit(3, "最新合集", _CAT_NEW, "magnet", priority=10),
        _unit(4, "亞洲無碼", _CAT_AREA, "magnet", priority=20),
        # 需登陆后免费购买
        _unit(5, "日本騎兵", _CAT_AREA, "magnet", priority=21),
        _unit(13, "歐美新片", _CAT_AREA, "magnet", priority=22),
        _unit(15, "國內原創", _CAT_AREA, "magnet", priority=23),
        _unit(16, "中字原創", _CAT_AREA, "magnet", priority=24),
        _unit(18, "三級寫真", _CAT_AREA, "magnet", priority=25),
        _unit(67, "正片大片", _CAT_AREA, "magnet", priority=26),
        _unit(343, "实时ＢＴ", _CAT_BT, "magnet", priority=30),
        _unit(195, "优质 BT", _CAT_BT, "magnet", priority=31),
        _unit(318, "磁链迅雷", _CAT_BT, "magnet", priority=32),
    ]
    return {u.key: u for u in units}


BOARD_POLICIES_2048: dict[str, BoardPolicy] = _build_policies_2048()

# 需登录 Cookie 才能看清下载链的板块（免费购买区）
LOGIN_REQUIRED_BOARD_FIDS_2048: frozenset[str] = frozenset({"5", "13"})

# 各白名单板常见置顶：回家指南 / 来访者必看 / 地址发布器 / 在线影院广告
SKIP_META_TIDS_2048: frozenset[int] = frozenset({4})
META_GUIDE_TITLE_HINTS_2048: tuple[str, ...] = (
    "回家指南",
    "地址发布器",
    "来访者必看",
    "乘访者必看",
    "访客必看",
    "使你更快速上手",
    "版块说明",
    "板块说明",
    "发帖必读",
    "发贴必读",
    "版规",
)
# 最新合集等板顶广告：无磁力/ED2K，勿入队
PROMO_AD_TITLE_HINTS_2048: tuple[str, ...] = (
    "在线影片",
    "超百万",
    "高速播放",
    "合集播放",
)


def is_2048_meta_guide_thread(title: str, tid: int | None = None) -> bool:
    """2048 白名单各板：版务/指南/发布器/广告置顶，不入队、判帖跳过。"""
    if tid is not None:
        try:
            if int(tid) in SKIP_META_TIDS_2048:
                return True
        except (TypeError, ValueError):
            pass
    t = (title or "").strip()
    if not t:
        return False
    if any(h in t for h in META_GUIDE_TITLE_HINTS_2048):
        return True
    if any(h in t for h in PROMO_AD_TITLE_HINTS_2048):
        return True
    # 多特征广告句：原档下载 + 同步更新 + 播放
    if "原档下载" in t and "同步更新" in t and "播放" in t:
        return True
    return False


_FID_DEFAULTS_2048: dict[int, BoardPolicy] = {}
for _u in BOARD_POLICIES_2048.values():
    if _u.fid not in _FID_DEFAULTS_2048:
        _FID_DEFAULTS_2048[_u.fid] = BoardPolicy(
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
            enabled=_u.enabled,
        )


def default_board_order_2048() -> list[str]:
    return [
        u.key
        for u in sorted(BOARD_POLICIES_2048.values(), key=lambda x: x.priority)
        if u.enabled
    ]


def expand_board_keys_2048(keys: list[str] | None) -> list[str]:
    """PHPWind 无 typeid 子版：只保留白名单内的纯 fid key。"""
    allowed = set(BOARD_POLICIES_2048.keys())
    out: list[str] = []
    seen: set[str] = set()
    for raw in keys or []:
        key = str(raw or "").strip()
        if not key or key in seen:
            continue
        if key in allowed:
            out.append(key)
            seen.add(key)
            continue
        if ":" in key:
            left = key.split(":", 1)[0].strip()
            if left in allowed and left not in seen:
                out.append(left)
                seen.add(left)
    return out


def get_board_policy_2048(fid_or_key: int | str) -> BoardPolicy:
    key = str(fid_or_key).strip()
    if key in BOARD_POLICIES_2048:
        return BOARD_POLICIES_2048[key]
    try:
        fid = int(key.split(":", 1)[0]) if key else 0
    except ValueError:
        fid = 0
    if fid in _FID_DEFAULTS_2048:
        return _FID_DEFAULTS_2048[fid]
    return BoardPolicy(key=key or str(fid), fid=fid or 0, name=f"fid-{fid}", category="其他")


# 管理端「结构化标签」芯片：站点实测高频【标签】（简繁异写入库时再归一）
# 须与 FORMAT_GUIDES_2048 字段、magnet 裸 hash 线索、resource_names 边界同源覆盖。
STRUCTURE_LABELS_2048: tuple[str, ...] = (
    "影片名称",
    "中文片名",
    "资源名称",
    "影片格式",
    "影片大小",
    "是否有码",
    "影片时间",
    "影片时长",
    "发布时间",
    "分辨率",
    "特征全码",
    "特征编码",
    "特征编号",
    "试证全码",
    "验证全码",
    "验证编码",
    "验证编号",
    "种子特码",
    "种子编码",
    "哈希校验",
    "作种期限",
    "种子期限",
    "图片预览",
    "影片预览",
    "影片截图",
    "有无水印",
    "资源类型",
    "资源数量",
    "下载方式",
)

FORMAT_GUIDES_2048: list[dict] = [
    {
        "id": "pw_bt_pack",
        "title": "BT 合集 / 磁链迅雷",
        "primary_link": "magnet",
        "fids": ["3", "318"],
        "summary": "一帖多部常见；主链磁力（.magnet-box / 正文），无磁力再 ED2K。",
        "fields": [
            "【影片名称】【中文片名】【影片格式】【是否有码】【影片时间】【影片大小】",
            "裸 hash：【特征全码】【特征编码】【特征编号】【试证全码】【验证全码】【验证编码】【验证编号】【种子特码】【种子编码】【哈希校验】",
            "【作种期限】【图片预览】【影片预览】【影片截图】",
            "ED2K 整理帖：【资源名称】【资源类型】【是否有码】【有无水印】【资源数量】【下载方式】",
        ],
        "notes": [
            "合集帖标签块会按子资源重复；片名以【影片名称】为准",
            "【试证全码】为帖内错别字（≈特征/验证），常与【资源大小】同行",
            "标题里的【中文破解】【BT种子】等是装饰，不是字段名",
        ],
    },
    {
        "id": "pw_area_bt",
        "title": "分区资源（亞洲無碼 / 國內原創等）",
        "primary_link": "magnet",
        "fids": ["4", "5", "13", "15", "16", "18"],
        "summary": "繁体标签居多；hash 多为【驗證全码】/【種子特碼】，亦见【试证全码】【特征全码】。",
        "fields": [
            "【影片名稱】【中文片名】【影片格式】【是否有碼】【影片時間】【影片大小】",
            "裸 hash：【驗證全码】【验证编号】【验证编码】【試證全码】【特徵全碼】【特征编码】【種子特碼】【种子编码】【哈希校验】",
            "【作種期限】【影片截圖】【影片預覽】【图片预览】",
        ],
        "notes": [
            "fid=5 日本騎兵、fid=13 歐美新片：需登录后免费购买才能看链",
            "简繁异写（名稱/名称、有碼/有码）一律归一入库",
        ],
    },
    {
        "id": "pw_live_bt",
        "title": "实时 / 优质 BT",
        "primary_link": "magnet",
        "fids": ["343", "195"],
        "summary": "短模板；343 片名常在标题，195 用【哈希校验】。",
        "fields": [
            "343：【发布时间】【影片格式】【影片大小】【影片时长】【分辨率】【影片预览】【图片预览】",
            "343 hash：【特征全码】【试证全码】【验证全码】【种子特码】【哈希校验】",
            "195：【影片名称】【影片大小】【影片格式】【影片时长】【哈希校验】【特征全码】【种子特码】【图片预览】",
        ],
        "notes": [
            "正文 #read_tpc；磁力多在 .magnet-box",
        ],
    },
    {
        "id": "pw_pan",
        "title": "正片大片（网盘）",
        "primary_link": "magnet",
        "fids": ["67"],
        "summary": "夸克等网盘帖【标签】不规范，尽量收磁力/ED2K，否则占位。",
        "fields": [
            "常见无规范【标签】；有则认：【影片名称】【资源名称】【影片大小】【资源大小】",
            "裸 hash（若出现）：【特征全码】【试证全码】【验证全码】【哈希校验】【种子特码】",
            "链多在正文或标题旁；网盘链跳过入库",
        ],
        "notes": [
            "配置与色花堂互不共用；Cookie 独立 jar",
        ],
    },
]
