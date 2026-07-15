"""Forum rules + per-forum crawler config APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.deps import require_permission
from db.connection import connect
from db.forum_configs import (
    FORUM_CRAWLER_DEFAULTS,
    SITE_CRAWLER_FORUM_ID,
    build_forums_payload,
    load_forum_configs_map,
    save_forum_config,
    set_active_board_fid,
    set_active_forum_id,
    set_enabled_board_fids,
)
from db.settings_store import get_setting
from workers.link_test import DEFAULT_TEST_URL, test_http_link
from api.zh_errors import user_facing_error
from workers.thread_parse_test import parse_thread_for_admin

router = APIRouter(prefix="/api/forum", tags=["forum"])

FORUM_DEFAULT_ENTRY_URLS: dict[str, str] = {
    SITE_CRAWLER_FORUM_ID: DEFAULT_TEST_URL,
}


class ForumConfigBody(BaseModel):
    config: dict = Field(default_factory=dict)


class ActiveForumBody(BaseModel):
    active_forum_id: str = Field(..., min_length=1, max_length=64)


class ActiveBoardBody(BaseModel):
    fid: str = Field(..., min_length=1, max_length=32)


class EnabledBoardsBody(BaseModel):
    fids: list[str] = Field(default_factory=list)


class ThreadParseBody(BaseModel):
    url: str = Field(..., min_length=1)
    fid: str = ""
    proxy: str = ""


@router.get("/rules")
def forum_rules(_user: dict = Depends(require_permission("settings.read"))) -> dict:
    conn = connect()
    try:
        return build_forums_payload(conn)
    finally:
        conn.close()


@router.put("/{forum_id}/config")
def put_forum_config(
    forum_id: str,
    body: ForumConfigBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    if forum_id != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入配置")
    conn = connect()
    try:
        saved = save_forum_config(conn, forum_id, body.config or {})
        return {"message": "success", "forum_id": forum_id, "config": saved}
    finally:
        conn.close()


@router.put("/active")
def put_active_forum(
    body: ActiveForumBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    if body.active_forum_id not in {SITE_CRAWLER_FORUM_ID}:
        raise HTTPException(status_code=400, detail="只能启用已接入的论坛")
    conn = connect()
    try:
        active = set_active_forum_id(conn, body.active_forum_id)
        return {"message": "success", "active_forum_id": active}
    finally:
        conn.close()


@router.put("/{forum_id}/active-board")
def put_active_board(
    forum_id: str,
    body: ActiveBoardBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    if forum_id != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入配置")
    conn = connect()
    try:
        saved = set_active_board_fid(conn, forum_id, body.fid)
        return {
            "message": "success",
            "forum_id": forum_id,
            "active_board_fid": saved.get("active_board_fid"),
            "enabled_board_fids": saved.get("enabled_board_fids"),
            "config": saved,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.put("/{forum_id}/enabled-boards")
def put_enabled_boards(
    forum_id: str,
    body: EnabledBoardsBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    if forum_id != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入配置")
    conn = connect()
    try:
        saved = set_enabled_board_fids(conn, forum_id, list(body.fids or []))
        return {
            "message": "success",
            "forum_id": forum_id,
            "enabled_board_fids": saved.get("enabled_board_fids"),
            "active_board_fid": saved.get("active_board_fid"),
            "config": saved,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post("/{forum_id}/link-test")
def forum_link_test(
    forum_id: str,
    _user: dict = Depends(require_permission("settings.read")),
) -> dict:
    fid = (forum_id or "").strip()
    if fid != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入联通检测")

    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        fc = configs.get(fid) or dict(FORUM_CRAWLER_DEFAULTS)
        proxy = get_setting(conn, "web_crawler_proxy", "")
    finally:
        conn.close()

    entry_urls = [item.strip() for item in str(fc.get("web_crawl_urls") or "").split(",") if item.strip()]
    test_url = entry_urls[0] if entry_urls else FORUM_DEFAULT_ENTRY_URLS.get(fid, "")
    if not test_url:
        raise HTTPException(status_code=400, detail="未配置论坛入口 URL")

    result = test_http_link(
        test_url,
        proxy=proxy,
        cookie=str(fc.get("web_crawler_cookie") or ""),
        user_agent=str(fc.get("web_crawler_ua") or ""),
        ok_message="论坛链接联通正常",
        fail_prefix="论坛链接访问失败",
    )
    return {"forum_id": fid, **result}


@router.post("/{forum_id}/parse-thread")
async def forum_parse_thread(
    forum_id: str,
    body: ThreadParseBody,
    _user: dict = Depends(require_permission("settings.read")),
) -> dict:
    """解析测试：浏览器过 18+，HTTP 读正文；不入库。"""
    fid = (forum_id or "").strip()
    if fid != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入解析测试")

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="帖子 URL 不能为空")

    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        fc = dict(configs.get(fid) or dict(FORUM_CRAWLER_DEFAULTS))
        site_proxy = get_setting(conn, "web_crawler_proxy", "")
    finally:
        conn.close()

    if site_proxy and not fc.get("web_crawler_proxy"):
        fc["web_crawler_proxy"] = site_proxy

    try:
        result = await parse_thread_for_admin(
            url,
            board_fid=body.fid.strip(),
            proxy_override=body.proxy.strip(),
            crawler_config=fc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=user_facing_error(exc, fallback="帖子 URL 无效")) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=user_facing_error(exc, fallback="解析失败，请稍后重试"),
        ) from exc

    return {"message": "解析完成", "forum_id": fid, **result}
