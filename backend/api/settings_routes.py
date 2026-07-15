"""Site-level settings (proxy) — 与拓扑「通用配置 / HTTP 代理」对齐。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth.deps import require_permission
from db.connection import connect
from db.settings_store import get_setting, save_settings

router = APIRouter(prefix="/api", tags=["settings"])

PROXY_KEY = "web_crawler_proxy"
SEARCH_FRONTEND_KEY = "search_frontend_url"


class SettingsBody(BaseModel):
    web_crawler_proxy: str = ""
    search_frontend_url: str = Field(default="http://localhost:3008")


@router.get("/settings")
def get_settings(_user: dict = Depends(require_permission("settings.read"))) -> dict:
    conn = connect()
    try:
        return {
            "web_crawler_proxy": get_setting(conn, PROXY_KEY, ""),
            "search_frontend_url": get_setting(conn, SEARCH_FRONTEND_KEY, "http://localhost:3008"),
            # 拓扑定稿：连续无间隔（轮间间隔固定 0，配置在论坛爬虫里）
            "web_crawler_interval_minutes": 0,
            "crawl_interval_label": "连续无间隔",
        }
    finally:
        conn.close()


@router.put("/settings")
def put_settings(
    body: SettingsBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    conn = connect()
    try:
        save_settings(
            conn,
            {
                PROXY_KEY: (body.web_crawler_proxy or "").strip(),
                SEARCH_FRONTEND_KEY: (body.search_frontend_url or "").strip()
                or "http://localhost:3008",
            },
        )
        return {
            "message": "success",
            "web_crawler_proxy": get_setting(conn, PROXY_KEY, ""),
            "search_frontend_url": get_setting(conn, SEARCH_FRONTEND_KEY, "http://localhost:3008"),
            "web_crawler_interval_minutes": 0,
            "crawl_interval_label": "连续无间隔",
        }
    finally:
        conn.close()
