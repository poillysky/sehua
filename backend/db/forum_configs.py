"""Per-forum crawler config + forum rules payload."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from db.settings_store import get_setting, save_settings
from parsers.boards import (
    BOARD_POLICIES,
    default_board_order,
    expand_legacy_board_keys,
    get_board_policy,
)

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
    # 账号登录 Cookie：仅「账号爬占位」使用；普通爬虫仍用 web_crawler_cookie
    "web_crawler_account_cookie": "",
    "web_crawler_auto_discover": False,
    "web_crawler_max_boards_per_run": 1,
    "web_crawler_list_pages_per_board": 15,
    # 已废弃：原每日自动首页捕新安全上限；手动扫新帖请用 web_crawler_manual_head_pages
    "web_crawler_list_head_pages": 50,
    # 手动「扫新帖」全局默认页数上限
    "web_crawler_manual_head_pages": 20,
    # 每板覆盖手动扫新帖上限，如 {"95": 30, "2": 10}
    "board_manual_head_pages": {},
    # 深扫连续 N 页所见均已入库则早停（已废弃给深扫用）；现供扫新帖早停：连续 N 页全已知结束，默认 2
    "web_crawler_list_known_stop_pages": 2,
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
    # 随机抓帖（tid 直链探测早期帖）
    "web_crawler_random_tid_min": 80_000,
    "web_crawler_random_tid_max": 500_000,
    "web_crawler_random_tid_probe": 200,
    "web_crawler_random_tid_import_target": 0,
    "board_order": default_board_order(),
    # 勾选参与爬取的子版（按 board_order 排序依次爬）；默认全开非版务
    "enabled_board_fids": default_board_order(),
    # 深扫当前工作子版（启用队列中的游标）
    "active_board_fid": default_board_order()[0],
    # 各板列表翻页游标：深扫向后推进；到底切板时仍保留，仅手动清除才删
    "board_list_cursors": {},
    # 各板「今日首页捕新已完成」日期 YYYY-MM-DD（上海时区）
    "board_head_catchup_on": {},
    # 各板当日首页捕新进度页（未扫完全已知时跨轮续扫；完成后清空）
    "board_head_progress": {},
    # 各板回填进度残留字段（已并入深扫；清游标时顺带清除）
    "board_backfill_progress": {},
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
        if key == "enabled_board_fids":
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
        if key == "board_manual_head_pages":
            if isinstance(val, dict):
                cleaned_m: dict[str, int] = {}
                for bf, pg in val.items():
                    try:
                        cleaned_m[str(bf)] = max(1, int(pg))
                    except (TypeError, ValueError):
                        continue
                base[key] = cleaned_m
            continue
        if key == "board_head_catchup_on":
            if isinstance(val, dict):
                cleaned_d: dict[str, str] = {}
                for bf, day in val.items():
                    s = str(day or "").strip()
                    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                        cleaned_d[str(bf)] = s[:10]
                base[key] = cleaned_d
            continue
        if key == "board_head_progress":
            if isinstance(val, dict):
                cleaned_p: dict[str, int] = {}
                for bf, pg in val.items():
                    try:
                        cleaned_p[str(bf)] = max(1, int(pg))
                    except (TypeError, ValueError):
                        continue
                base[key] = cleaned_p
            continue
        if key == "board_backfill_progress":
            if isinstance(val, dict):
                cleaned_bf: dict[str, int] = {}
                for bf, pg in val.items():
                    try:
                        cleaned_bf[str(bf)] = max(1, int(pg))
                    except (TypeError, ValueError):
                        continue
                base[key] = cleaned_bf
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
    # 启用队列长度作提示；实际按板依次处理，不再限制「每轮多板并发」
    try:
        base["web_crawler_max_boards_per_run"] = max(
            1, int(base.get("web_crawler_max_boards_per_run") or 1)
        )
    except (TypeError, ValueError):
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
    # 爬取单位 key（如 95:716）；旧纯 fid 自动展开为全部子版
    allowed = set(BOARD_POLICIES.keys())
    default_order = default_board_order()
    raw_order = expand_legacy_board_keys(
        [str(x) for x in (base.get("board_order") or [])]
    )
    order = [k for k in raw_order if k in allowed]
    for key in default_order:
        if key not in order:
            order.append(key)
    base["board_order"] = order

    # 启用队列：按 board_order 排序；旧配置无 enabled 时用 active 迁移并展开
    if "enabled_board_fids" not in (raw or {}):
        legacy_active = str(base.get("active_board_fid") or "").strip()
        expanded = expand_legacy_board_keys([legacy_active] if legacy_active else [])
        enabled = [k for k in order if k in set(expanded)]
        if not enabled:
            enabled = [order[0]] if order else [default_order[0]]
    else:
        raw_enabled = expand_legacy_board_keys(
            [str(x) for x in (base.get("enabled_board_fids") or [])]
        )
        enabled = [k for k in order if k in set(raw_enabled)]
        if not enabled:
            legacy_active = str(base.get("active_board_fid") or "").strip()
            expanded = expand_legacy_board_keys([legacy_active] if legacy_active else [])
            enabled = [k for k in order if k in set(expanded)]
            if not enabled:
                enabled = [order[0]] if order else [default_order[0]]
    base["enabled_board_fids"] = enabled

    # active：纯 fid → 展开后的第一子版
    active = str(base.get("active_board_fid") or "").strip()
    if active not in enabled:
        expanded_active = expand_legacy_board_keys([active] if active else [])
        pick = next((k for k in enabled if k in set(expanded_active)), None)
        base["active_board_fid"] = pick or enabled[0]
    else:
        base["active_board_fid"] = active
    base["web_crawler_max_boards_per_run"] = max(1, len(enabled))

    # 游标：只保留二级单位 key；纯 fid 主板旧游标直接丢弃（页码与子版列表不可对应）
    cursors = dict(base.get("board_list_cursors") or {})
    migrated_cursors: dict[str, int] = {}
    for ck, pg in cursors.items():
        ck_s = str(ck)
        if ck_s in allowed:
            try:
                migrated_cursors[ck_s] = max(0, int(pg))
            except (TypeError, ValueError):
                continue
        # 纯数字 fid：丢弃，不迁到任一子版
    base["board_list_cursors"] = migrated_cursors

    for map_key in (
        "board_manual_head_pages",
        "board_head_catchup_on",
        "board_head_progress",
        "board_backfill_progress",
    ):
        raw_map = base.get(map_key)
        if not isinstance(raw_map, dict):
            base[map_key] = {}
            continue
        migrated: dict[str, Any] = {}
        for ck, val in raw_map.items():
            ck_s = str(ck)
            if ck_s in allowed:
                migrated[ck_s] = val
            # 纯 fid：丢弃，不迁移
        base[map_key] = migrated
    if not isinstance(base.get("board_list_cursors"), dict):
        base["board_list_cursors"] = {}
    if not isinstance(base.get("board_manual_head_pages"), dict):
        base["board_manual_head_pages"] = {}
    if not isinstance(base.get("board_head_catchup_on"), dict):
        base["board_head_catchup_on"] = {}
    if not isinstance(base.get("board_head_progress"), dict):
        base["board_head_progress"] = {}
    if not isinstance(base.get("board_backfill_progress"), dict):
        base["board_backfill_progress"] = {}
    try:
        base["web_crawler_manual_head_pages"] = max(
            1, int(base.get("web_crawler_manual_head_pages") or 20)
        )
    except (TypeError, ValueError):
        base["web_crawler_manual_head_pages"] = 20
    return base


def resolve_enabled_board_fids(cfg: dict[str, Any] | None) -> list[str]:
    """启用爬取队列：按 board_order 排序后的 enabled_board_fids（单位 key）。"""
    allowed = set(BOARD_POLICIES.keys())
    order = expand_legacy_board_keys(
        [str(x) for x in ((cfg or {}).get("board_order") or [])]
    )
    order = [k for k in order if k in allowed]
    if not order:
        order = [k for k in default_board_order() if k in allowed]
    raw = expand_legacy_board_keys(
        [str(x) for x in ((cfg or {}).get("enabled_board_fids") or [])]
    )
    enabled = [k for k in order if k in set(raw)]
    if enabled:
        return enabled
    active = str((cfg or {}).get("active_board_fid") or "").strip()
    expanded = expand_legacy_board_keys([active] if active else [])
    pick = [k for k in order if k in set(expanded)]
    if pick:
        return pick
    return [order[0]] if order else []


def next_enabled_board_fid(cfg: dict[str, Any] | None, current: str | int | None) -> str:
    """启用队列中下一板（到尾后回绕到首板）。"""
    boards = resolve_enabled_board_fids(cfg)
    if not boards:
        return str(current or "")
    cur = str(current or "").strip()
    if cur not in boards:
        return boards[0]
    return boards[(boards.index(cur) + 1) % len(boards)]


def resolve_manual_head_pages(cfg: dict[str, Any] | None, board_fid: str | int) -> int:
    """手动扫新帖页数上限：每板覆盖优先，否则全局默认。"""
    raw = (cfg or {}).get("board_manual_head_pages") or {}
    fid = str(board_fid)
    if isinstance(raw, dict) and fid in raw:
        try:
            return max(1, int(raw[fid]))
        except (TypeError, ValueError):
            pass
    try:
        return max(1, int((cfg or {}).get("web_crawler_manual_head_pages") or 20))
    except (TypeError, ValueError):
        return 20


def crawl_today() -> str:
    """爬虫「自然日」：Asia/Shanghai 的 YYYY-MM-DD。"""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except Exception:
        return date.today().isoformat()


def get_board_head_catchup_on(cfg: dict[str, Any] | None, board_fid: str | int) -> str:
    raw = (cfg or {}).get("board_head_catchup_on") or {}
    if not isinstance(raw, dict):
        return ""
    return str(raw.get(str(board_fid)) or "").strip()[:10]


def is_board_head_done_today(cfg: dict[str, Any] | None, board_fid: str | int) -> bool:
    return get_board_head_catchup_on(cfg, board_fid) == crawl_today()


def get_board_head_progress(cfg: dict[str, Any] | None, board_fid: str | int) -> int:
    raw = (cfg or {}).get("board_head_progress") or {}
    if not isinstance(raw, dict):
        return 1
    try:
        return max(1, int(raw.get(str(board_fid)) or 1))
    except (TypeError, ValueError):
        return 1


def set_board_head_catchup_state(
    conn: Any,
    forum_id: str,
    board_fid: str | int,
    *,
    done_today: bool = False,
    progress_page: int | None = None,
    clear_progress: bool = False,
) -> dict:
    """更新当日首页捕新状态。done_today=True 时写入今日日期并清空进度。"""
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    key = str(board_fid)
    dates = dict(current.get("board_head_catchup_on") or {})
    progress = dict(current.get("board_head_progress") or {})
    if done_today:
        dates[key] = crawl_today()
        progress.pop(key, None)
    elif clear_progress:
        progress.pop(key, None)
    elif progress_page is not None:
        progress[key] = max(1, int(progress_page))
    current["board_head_catchup_on"] = dates
    current["board_head_progress"] = progress
    return save_forum_config(conn, forum_id, current)


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
    """持久化列表翻页游标；reset=True 时清零（仅手动清除游标时使用）。"""
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


def clear_board_cursor(
    conn: Any,
    forum_id: str,
    board_fid: str | int,
) -> dict:
    """清除某二级子版深扫游标，并清掉残留回填进度；下次深扫从列表头起。"""
    from parsers.boards import BOARD_POLICIES, expand_legacy_board_keys

    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    allowed = set(BOARD_POLICIES.keys())
    expanded = expand_legacy_board_keys([str(board_fid).strip()])
    key = next((k for k in expanded if k in allowed), "")
    if not key:
        key = str(board_fid).strip()
    if key not in allowed:
        raise ValueError(f"子版 {board_fid} 不在白名单")
    cursors = dict(current.get("board_list_cursors") or {})
    cursors.pop(key, None)
    current["board_list_cursors"] = cursors
    progress = dict(current.get("board_backfill_progress") or {})
    progress.pop(key, None)
    current["board_backfill_progress"] = progress
    return save_forum_config(conn, forum_id, current)


def get_board_backfill_progress(cfg: dict[str, Any] | None, board_fid: str | int) -> int:
    """回填下一页（默认 1）；独立于深扫游标。"""
    raw = (cfg or {}).get("board_backfill_progress") or {}
    if not isinstance(raw, dict):
        return 1
    try:
        return max(1, int(raw.get(str(board_fid)) or 1))
    except (TypeError, ValueError):
        return 1


def set_board_backfill_progress(
    conn: Any,
    forum_id: str,
    board_fid: str | int,
    page: int | None,
    *,
    clear: bool = False,
) -> dict:
    """持久化回填进度。clear=True 或 page=None 时清除该板进度。"""
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    progress = dict(current.get("board_backfill_progress") or {})
    key = str(board_fid)
    if clear or page is None:
        progress.pop(key, None)
    else:
        progress[key] = max(1, int(page))
    current["board_backfill_progress"] = progress
    return save_forum_config(conn, forum_id, current)


def set_active_board_fid(conn: Any, forum_id: str, board_fid: str) -> dict:
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    allowed = set(BOARD_POLICIES.keys())
    expanded = expand_legacy_board_keys([str(board_fid).strip()])
    fid = next((k for k in expanded if k in allowed), "")
    if not fid:
        fid = str(board_fid).strip()
    if fid not in allowed:
        raise ValueError(f"子版 {board_fid} 不在白名单")
    enabled = list(resolve_enabled_board_fids(current))
    if fid not in enabled:
        enabled.append(fid)
        order = [str(x) for x in (current.get("board_order") or [])]
        enabled = [k for k in order if k in set(enabled)] or enabled
    current["enabled_board_fids"] = enabled
    current["active_board_fid"] = fid
    current["web_crawler_max_boards_per_run"] = max(1, len(enabled))
    return save_forum_config(conn, forum_id, current)


def set_enabled_board_fids(conn: Any, forum_id: str, board_fids: list[str]) -> dict:
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    allowed = set(BOARD_POLICIES.keys())
    order = expand_legacy_board_keys(
        [str(x) for x in (current.get("board_order") or default_board_order())]
    )
    order = [k for k in order if k in allowed] or default_board_order()
    wanted = set(expand_legacy_board_keys([str(x) for x in (board_fids or [])]))
    enabled = [k for k in order if k in wanted and k in allowed]
    if not enabled:
        raise ValueError("请至少启用一个子版")
    current["board_order"] = order
    current["enabled_board_fids"] = enabled
    active = str(current.get("active_board_fid") or "").strip()
    if active not in enabled:
        current["active_board_fid"] = enabled[0]
    current["web_crawler_max_boards_per_run"] = max(1, len(enabled))
    return save_forum_config(conn, forum_id, current)


def advance_active_board_fid(conn: Any, forum_id: str, *, from_fid: str | int | None = None) -> dict:
    """深扫某板到底后切到启用队列下一板。"""
    configs = load_forum_configs_map(conn)
    current = dict(configs.get(forum_id) or default_forum_crawler_config())
    cur = str(from_fid or current.get("active_board_fid") or "").strip()
    nxt = next_enabled_board_fid(current, cur)
    current["active_board_fid"] = nxt
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
        "title": "综合讨论区（情色分享）",
        "primary_link": "ed2k",
        "fids": ["95"],
        "summary": "仅爬取 typeid=716 情色分享；列表带分类过滤。",
        "fields": [
            "【资源名称】【资源类型】【资源大小】【是否有码】",
            "【有无第三方水印】【解压密码】（可选）",
        ],
        "notes": [
            "列表带 typeid 过滤；按发帖时间翻页",
            "正文无链再读帖尾附件；无权限或无链则占位入库",
            "不写预览、剧情截图、证明图",
        ],
    },
    {
        "id": "discuz_141",
        "title": "网友原创区（按分类子版）",
        "primary_link": "ed2k",
        "fids": ["141"],
        "summary": "国产/欧美/日本合集等分类分爬；电驴链常在附件。",
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
        "title": "转帖交流区（按分类子版）",
        "primary_link": "magnet",
        "fids": ["142"],
        "summary": "国产自拍/亚洲有码等分类分爬；磁力可能在正文或附件。",
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
            "key": b.key,
            "fid": str(b.fid),
            "typeid": b.list_typeid or "",
            "name": b.name,
            "board_name": b.board_name or b.name,
            "type_name": b.type_name or "",
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
