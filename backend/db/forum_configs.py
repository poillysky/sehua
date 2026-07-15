"""Per-forum crawler config + forum rules payload."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from db.settings_store import get_setting, save_settings
from parsers.boards import BOARD_POLICIES, default_board_order

FORUM_CONFIG_KEY = "forum_configs"
ACTIVE_FORUM_KEY = "active_forum_id"

# 官方永久入口（Telegram 频道公布）；逗号分隔，爬虫按序尝试
DEFAULT_WEB_CRAWL_URLS = ",".join(
    [
        "https://www.sehuatang.net/forum.php",
        "https://www.sehuatang.org/forum.php",
        "https://sehuatang.com/forum.php",
        "https://98tang.com/forum.php",
        "https://98t.la/forum.php",
    ]
)
_LEGACY_WEB_CRAWL_URLS = {
    "https://www.sehuatang.net/forum.php",
    "https://sehuatang.net/forum.php",
}

FORUM_CRAWLER_DEFAULTS: dict[str, Any] = {
    "web_crawler_enabled": True,
    "web_crawl_urls": DEFAULT_WEB_CRAWL_URLS,
    # 本站连续爬取：轮间无间隔（仅保留请求延迟 / 失败冷却）
    "web_crawler_interval_minutes": 0,
    "web_crawler_timeout": 30,
    "web_crawler_ua": "",
    "web_crawler_cookie": "safe=1",
    "web_crawler_auto_discover": False,
    "web_crawler_max_boards_per_run": 1,
    "web_crawler_list_pages_per_board": 15,
    "web_crawler_board_refresh_hours": 12,
    "web_crawler_max_threads_per_run": 0,
    "web_crawler_request_delay": 2.0,
    "web_crawler_fetch_failure_threshold": 5,
    "web_crawler_fetch_cooldown_seconds": 45,
    "web_crawler_fetch_max_cooldowns": 3,
    "web_crawler_autothrottle_max_delay": 60.0,
    "web_crawler_autothrottle_window": 20,
    "web_crawler_target_imports": 0,
    "web_crawler_require_structured_desc": False,
    "web_crawler_one_link_per_thread": True,
    "web_crawler_max_list_pages": 0,
    "web_crawler_fetch_retries": 3,
    "web_crawler_thread_timeout": 120,
    "board_order": default_board_order(),
    # 本站爬虫一次只跑一个工作板块（在「板块列表」里单选）
    "active_board_fid": default_board_order()[0],
    # 各板列表翻页游标：所见均已入库时继续往后；有新帖后从该页起按 pages_per_board 计数
    "board_list_cursors": {},
}


def default_forum_crawler_config() -> dict[str, Any]:
    return deepcopy(FORUM_CRAWLER_DEFAULTS)


def _normalize_forum_config(raw: dict | None) -> dict[str, Any]:
    base = default_forum_crawler_config()
    if not raw:
        return base
    for key, default in list(base.items()):
        if key not in raw:
            continue
        val = raw[key]
        if key == "board_order":
            if isinstance(val, list):
                base[key] = [str(item).strip() for item in val if str(item).strip()]
            elif isinstance(val, str):
                base[key] = [item.strip() for item in val.split(",") if item.strip()]
            continue
        if key == "board_list_cursors":
            if isinstance(val, dict):
                cleaned: dict[str, int] = {}
                for bf, pg in val.items():
                    try:
                        cleaned[str(bf)] = max(0, int(pg))
                    except (TypeError, ValueError):
                        continue
                base[key] = cleaned
            continue
        if isinstance(default, bool):
            base[key] = bool(val) if isinstance(val, bool) else str(val).lower() in {"1", "true", "yes", "on"}
        elif isinstance(default, int) and not isinstance(default, bool):
            try:
                base[key] = int(val)
            except (TypeError, ValueError):
                pass
        elif isinstance(default, float):
            try:
                base[key] = float(val)
            except (TypeError, ValueError):
                pass
        else:
            base[key] = str(val)
    base["web_crawler_one_link_per_thread"] = True
    base["web_crawler_require_structured_desc"] = False
    # 拓扑：仅白名单工作板，不做自动发现
    base["web_crawler_auto_discover"] = False
    # 本站模型：每轮最多扫 1 个板块；工作板块必须落在白名单内
    base["web_crawler_max_boards_per_run"] = 1
    # 本站连续爬取：关闭轮间间隔
    base["web_crawler_interval_minutes"] = 0
    # 本批帖数上限：0 = 不另限（深扫入队多少抓多少，仍受目标入库约束）
    if int(base.get("web_crawler_max_threads_per_run") or 0) < 0:
        base["web_crawler_max_threads_per_run"] = 0
    # 旧库仅一条主域时，升级为官方永久域名列表（用户自定义多地址则保留）
    crawl_urls = [u.strip() for u in str(base.get("web_crawl_urls") or "").split(",") if u.strip()]
    if not crawl_urls or (len(crawl_urls) == 1 and crawl_urls[0].rstrip("/") in _LEGACY_WEB_CRAWL_URLS):
        base["web_crawl_urls"] = DEFAULT_WEB_CRAWL_URLS
    allowed = {str(fid) for fid in BOARD_POLICIES}
    # 合并新增白名单 fid 到 board_order（旧配置升级时自动补齐）
    order = [str(x) for x in (base.get("board_order") or []) if str(x) in allowed]
    for fid in default_board_order():
        if fid not in order:
            order.append(fid)
    base["board_order"] = order
    active = str(base.get("active_board_fid") or "").strip()
    if active not in allowed:
        base["active_board_fid"] = order[0] if order else default_board_order()[0]
    else:
        base["active_board_fid"] = active
    if not isinstance(base.get("board_list_cursors"), dict):
        base["board_list_cursors"] = {}
    return base


def get_board_list_cursor(cfg: dict[str, Any] | None, board_fid: str | int) -> int:
    cursors = (cfg or {}).get("board_list_cursors") or {}
    if not isinstance(cursors, dict):
        return 0
    try:
        return max(0, int(cursors.get(str(board_fid)) or 0))
    except (TypeError, ValueError):
        return 0


def set_board_list_cursor(
    conn: Any,
    forum_id: str,
    board_fid: str | int,
    page: int,
    *,
    reset: bool = False,
) -> dict:
    """持久化列表翻页游标；reset=True 时清零（列表到底后下一轮从头）。"""
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    cursors = dict(current.get("board_list_cursors") or {})
    key = str(board_fid)
    if reset:
        cursors.pop(key, None)
    else:
        cursors[key] = max(0, int(page or 0))
    current["board_list_cursors"] = cursors
    return save_forum_config(conn, forum_id, current)


def set_active_board_fid(conn: Any, forum_id: str, board_fid: str) -> dict:
    fid = str(board_fid or "").strip()
    if fid not in {str(x) for x in BOARD_POLICIES}:
        raise ValueError(f"板块 fid={fid} 不在白名单")
    configs = load_forum_configs_map(conn)
    current = configs.get(forum_id) or default_forum_crawler_config()
    current["active_board_fid"] = fid
    current["web_crawler_max_boards_per_run"] = 1
    return save_forum_config(conn, forum_id, current)


def load_forum_configs_map(conn: Any) -> dict[str, dict]:
    blob = get_setting(conn, FORUM_CONFIG_KEY, "").strip()
    if not blob:
        return {"sehuatang": default_forum_crawler_config()}
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return {"sehuatang": default_forum_crawler_config()}
    if not isinstance(parsed, dict):
        return {"sehuatang": default_forum_crawler_config()}
    out = {str(fid): _normalize_forum_config(cfg if isinstance(cfg, dict) else None) for fid, cfg in parsed.items()}
    if "sehuatang" not in out:
        out["sehuatang"] = default_forum_crawler_config()
    return out


def save_forum_config(conn: Any, forum_id: str, config: dict) -> dict:
    configs = load_forum_configs_map(conn)
    normalized = _normalize_forum_config(config)
    configs[forum_id] = normalized
    save_settings(conn, {FORUM_CONFIG_KEY: json.dumps(configs, ensure_ascii=False)})
    return normalized


def get_active_forum_id(conn: Any) -> str:
    return get_setting(conn, ACTIVE_FORUM_KEY, "sehuatang") or "sehuatang"


def set_active_forum_id(conn: Any, forum_id: str) -> str:
    fid = (forum_id or "sehuatang").strip() or "sehuatang"
    save_settings(conn, {ACTIVE_FORUM_KEY: fid})
    return fid


# 本站仅色花堂有专用爬虫；后续论坛注册时必须提供独立模块，配置不与 sehuatang 共用。
SITE_CRAWLER_FORUM_ID = "sehuatang"
SITE_CRAWLER_MODULE = "crawler.sehuatang"

# 正文【标签】展示名（供管理端；入库别名见 parsers.content.LABEL_KEYS）
STRUCTURE_LABELS = (
    "影片名称",
    "资源名称",
    "影片容量",
    "资源大小",
    "是否有码",
    "有无水印",
    "出演女优",
    "解压密码",
)

FORMAT_GUIDES: list[dict[str, Any]] = [
    {
        "id": "bt_magnet",
        "title": "原创电影（磁力）",
        "primary_link": "magnet",
        "fids": ["2", "36", "37", "103", "107", "160", "104", "38", "151", "152", "39"],
        "summary": "正文找磁力；没有磁力再解析种子附件。韩国主播、动漫区标签略异。",
        "fields": [
            "【影片名称】【出演女优】【影片容量】或【影片大小】【是否有码】",
            "韩国主播可有【影片格式】；动漫可有【影片码别】",
        ],
        "notes": [
            "列表按发帖时间；每帖一条主资源，同帖多磁力可一并记下",
            "跳过鲍鱼直播盒子；不写种子期限、下载工具、预览类标签",
            "入库：影片名称→资源名称，容量/大小→文件大小",
        ],
    },
    {
        "id": "discuz_95",
        "title": "综合讨论区 · 情色分享",
        "primary_link": "ed2k",
        "fids": ["95"],
        "summary": "只爬情色分享一类帖；电驴链在正文或帖尾附件。",
        "fields": [
            "【资源名称】【资源类型】【资源大小】【是否有码】",
            "【有无第三方水印】【解压密码】（可选）",
        ],
        "notes": [
            "其它主题分类不爬；列表按发帖时间",
            "正文无链再读帖尾附件；无权限或无链则占位入库",
            "不写预览、剧情截图、证明图",
        ],
    },
    {
        "id": "discuz_141",
        "title": "网友原创区",
        "primary_link": "ed2k",
        "fids": ["141"],
        "summary": "多为合集帖；电驴链常在附件里，需浏览器下载。",
        "fields": [
            "【资源名称】【资源类型】【资源数量】【资源大小】",
            "【有无水印】或【是否有码】【解压密码】（如有）",
        ],
        "notes": [
            "只收发帖满三天的帖；列表按发帖时间",
            "下附件需已登录；不写下载方式、目录清单",
        ],
    },
    {
        "id": "discuz_142",
        "title": "转帖交流区",
        "primary_link": "magnet",
        "fids": ["142"],
        "summary": "转帖标签常不齐；磁力在正文、折叠区或附件都可能出现。",
        "fields": [
            "【资源名称】或【影片名称】",
            "【文件大小】或【影片大小】【是否有码】（均可选）",
        ],
        "notes": [
            "标签不全也能入库；无名称用帖题顶上",
            "无下载链则占位入库",
        ],
    },
]


def build_forums_payload(conn: Any) -> dict:
    configs = load_forum_configs_map(conn)
    boards = [
        {
            "fid": str(b.fid),
            "name": b.name,
            "category": b.category,
            "primary_link": b.primary_link,
            "hot": b.hot,
            "priority": b.priority,
            "enabled": b.enabled,
        }
        for b in sorted(BOARD_POLICIES.values(), key=lambda x: x.priority)
        if b.enabled
    ]
    sehuatang_cfg = configs.get(SITE_CRAWLER_FORUM_ID, default_forum_crawler_config())
    # 仅返回已登记论坛的独立配置；planned 论坛不预填色花堂通用字段
    dedicated_configs = {
        fid: cfg for fid, cfg in configs.items() if fid == SITE_CRAWLER_FORUM_ID
    }
    forums = [
        {
            "id": SITE_CRAWLER_FORUM_ID,
            "name": "色花堂",
            "base_url": "https://www.sehuatang.net/",
            "status": "active",
            "site_dedicated": True,
            "crawler_registered": True,
            "crawler_module": SITE_CRAWLER_MODULE,
            "board_count": len(boards),
            "boards": boards,
            "crawler_config": sehuatang_cfg,
            "structure_labels": list(STRUCTURE_LABELS),
            "format_guides": FORMAT_GUIDES,
            "policies": [
                "本站专用爬虫：仅服务色花堂，配置不与其他论坛共用",
                "一次仅选一个工作板块进行采集",
                "原创BT电影：除 fid 148（鲍鱼直播盒子）外白名单板块（磁力为主）",
                "综合讨论区：fid=95 仅 typeid=716 情色分享 ED2K；141 网友原创 ED2K；142 转帖交流区磁力",
                "网友原创区（fid=141）：只爬发帖时间满 3 天的帖子",
                "不爬：在线视频区、原档收藏、色花图片、色花文学",
            ],
        },
        {
            "id": "other",
            "name": "其他论坛",
            "base_url": "",
            "status": "planned",
            "site_dedicated": False,
            "crawler_registered": False,
            "crawler_module": None,
            "board_count": 0,
            "boards": [],
            # 故意不返回色花堂默认配置，避免误用为「通用模板」
            "crawler_config": None,
            "policies": [
                "待独立开发专用爬虫模块后接入",
                "配置与色花堂互不共用，不可套用本站字段",
            ],
        },
    ]
    return {
        "active_forum_id": get_active_forum_id(conn),
        "site_crawler_forum_id": SITE_CRAWLER_FORUM_ID,
        "forums": forums,
        "forum_configs": dedicated_configs,
        "registered_crawler_forums": [SITE_CRAWLER_FORUM_ID],
    }
