"""人工导入：标准说明 + 按统一入库格式表单入库。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth.deps import require_permission
from db.resource_db import connect_resource
from db.repository import ensure_source, upsert_resource
from parsers.ed2k import Ed2kLink, parse_ed2k_text
from parsers.magnet import parse_magnet_text

router = APIRouter(prefix="/api/import", tags=["import"])

PREVIEW_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads" / "previews"
PREVIEW_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PREVIEW_MAX_BYTES = 4 * 1024 * 1024
PREVIEW_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

RESOURCE_FORMAT = [
    {"no": 1, "name": "标题", "note": "可选；空则用链接内文件名", "key": "title"},
    {"no": 2, "name": "文件大小", "note": "字节数；空则用链接内大小", "key": "file_size"},
    {"no": 3, "name": "预览图", "note": "最多 5 张；可上传或粘贴 URL", "key": "preview_images"},
    {"no": 4, "name": "来源论坛名", "note": "如：色花堂", "key": "forum_name"},
    {"no": 5, "name": "来源板块名", "note": "含子分类，如：国产原创 · 国产无码", "key": "board_name"},
    {"no": 6, "name": "magnet 或 ED2K 链接", "note": "必填；可多行", "key": "links"},
    {"no": 7, "name": "帖子原链接", "note": "可选 source_url", "key": "source_url"},
    {"no": 8, "name": "资源解压密码", "note": "可选", "key": "extract_password"},
]


class ImportBody(BaseModel):
    """与统一入库格式 1–8 对应。"""

    title: str = ""
    file_size: int | None = Field(default=None, ge=0)
    preview_images: list[str] = Field(default_factory=list)
    forum_name: str = ""
    board_name: str = ""
    links: str = Field(default="", description="magnet / ED2K 文本")
    # 兼容旧字段
    content: str = ""
    source_url: str = ""
    extract_password: str = ""


class ImportResult(BaseModel):
    count: int
    message: str = "success"
    ed2k: int = 0
    magnets: int = 0


def _parse_preview_images(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\n,;]+", raw)
    else:
        parts = []
        for item in raw:
            parts.extend(re.split(r"[\n,;]+", str(item)))
    out: list[str] = []
    for p in parts:
        u = p.strip()
        if u and u not in out:
            out.append(u)
        if len(out) >= 5:
            break
    return out


def _collect_links(text: str) -> tuple[list[Ed2kLink], int, int]:
    ed2k = parse_ed2k_text(text)
    magnets = parse_magnet_text(text)
    out: list[Ed2kLink] = list(ed2k)
    seen = {x.hash for x in out}
    for m in magnets:
        h = (m.infohash or "").upper()
        if not h or h in seen:
            continue
        seen.add(h)
        out.append(
            Ed2kLink(
                filename=m.filename or f"magnet-{h[:8]}",
                size=int(m.size or 0),
                hash=h,
                link=m.link,
            )
        )
    return out, len(ed2k), len(magnets)


def import_links(
    conn,
    text: str,
    *,
    source_url: str | None = None,
    title: str | None = None,
    file_size: int | None = None,
    preview_images: list[str] | None = None,
    forum_name: str | None = None,
    board_name: str | None = None,
    extract_password: str | None = None,
) -> ImportResult:
    links, n_ed2k, n_magnet = _collect_links(text)
    if not links:
        raise ValueError("未识别到 ED2K 或 magnet 链接")
    source_id = ensure_source(conn, "upload:manual", "手动上传", "upload")
    images = _parse_preview_images(preview_images)
    size_override = int(file_size) if file_size is not None and int(file_size) > 0 else None
    forum = (forum_name or "").strip() or "sehuatang"
    # 中文论坛名归一化到 forum_id，便于展示与筛选
    _forum_aliases = {
        "色花堂": "sehuatang",
        "sehua": "sehuatang",
        "98堂": "sehuatang",
        "其他": "other",
        "其他论坛": "other",
    }
    forum = _forum_aliases.get(forum, forum)
    board = (board_name or "").strip() or None
    pwd = (extract_password or "").strip() or None
    src = (source_url or "").strip() or None
    ttl = (title or "").strip() or None

    for link in links:
        sized = (
            Ed2kLink(
                filename=link.filename,
                size=size_override if size_override is not None else link.size,
                hash=link.hash,
                link=link.link,
            )
            if size_override is not None
            else link
        )
        upsert_resource(
            conn,
            sized,
            source_id,
            source_url=src,
            title=ttl or sized.filename,
            preview_images=images or None,
            ed2k_links=[sized.link],
            extract_password=pwd,
            board_name=board,
            forum_id=forum,
            commit=False,
        )
    conn.commit()
    return ImportResult(count=len(links), ed2k=n_ed2k, magnets=n_magnet)


@router.get("/spec")
def import_spec(_user: dict = Depends(require_permission("settings.read"))) -> dict:
    return {
        "title": "快速导入",
        "goal": "按统一入库格式填写；第 6 项链接必填，其余可选。与论坛爬取共用同一库表。",
        "resource_format": RESOURCE_FORMAT,
        "ed2k_format": "ed2k://|file|<文件名>|<字节数>|<32位hash>|/",
        "magnet_format": "magnet:?xt=urn:btih:<infohash>&dn=<文件名>&xl=<字节数>",
        "filename_rules": [
            "建议前缀 www.98T.la@（色花堂版规常见写法）",
            "示例：www.98T.la@影片名称.mp4",
        ],
        "input_methods": [
            "表单逐项填写（推荐）",
            "预览图可本地上传或粘贴 URL",
            "链接区可粘贴多行，或从 txt 填入",
        ],
        "example": "ed2k://|file|www.98T.la@示例影片.mp4|2147483648|766C163CF5DDE96E597B333D550D1204|/",
        "notes": [
            "第 6 项链接必填",
            "预览图最多 5 张",
            "文件大小留空则使用链接内数值",
        ],
    }


@router.post("/preview")
async def upload_preview_images(
    files: list[UploadFile] = File(...),
    _user: dict = Depends(require_permission("import")),
) -> dict:
    """上传预览图，返回可入库的 URL 列表（最多 5 张）。"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择预览图")
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    urls: list[str] = []
    for file in files[:5]:
        raw = await file.read()
        if not raw:
            continue
        if len(raw) > PREVIEW_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"{file.filename or '图片'} 超过 4MB")
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        suffix = PREVIEW_MIME.get(content_type)
        if not suffix:
            name = (file.filename or "").lower()
            ext = Path(name).suffix
            if ext not in PREVIEW_EXT:
                raise HTTPException(status_code=400, detail="仅支持 jpg / png / webp / gif")
            suffix = ext if ext != ".jpeg" else ".jpg"
        name = f"{uuid.uuid4().hex}{suffix}"
        (PREVIEW_DIR / name).write_bytes(raw)
        urls.append(f"/static/previews/{name}")
    if not urls:
        raise HTTPException(status_code=400, detail="未上传到有效图片")
    return {"urls": urls, "count": len(urls)}


@router.post("/", response_model=ImportResult)
@router.post("", response_model=ImportResult, include_in_schema=False)
def import_text(
    body: ImportBody,
    _user: dict = Depends(require_permission("import")),
) -> ImportResult:
    text = (body.links or body.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请填写 magnet 或 ED2K 链接")
    conn = connect_resource()
    try:
        return import_links(
            conn,
            text,
            source_url=body.source_url,
            title=body.title,
            file_size=body.file_size,
            preview_images=body.preview_images,
            forum_name=body.forum_name,
            board_name=body.board_name,
            extract_password=body.extract_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post("/file", response_model=ImportResult)
async def import_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    file_size: str = Form(""),
    preview_images: str = Form(""),
    forum_name: str = Form(""),
    board_name: str = Form(""),
    source_url: str = Form(""),
    extract_password: str = Form(""),
    _user: dict = Depends(require_permission("import")),
) -> ImportResult:
    raw = await file.read()
    content = ""
    for encoding in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not content.strip():
        raise HTTPException(status_code=400, detail="无法解码上传文件或文件为空")

    size_val: int | None = None
    if str(file_size).strip().isdigit():
        size_val = int(str(file_size).strip())

    conn = connect_resource()
    try:
        return import_links(
            conn,
            content,
            source_url=source_url,
            title=title or (file.filename or "").strip() or None,
            file_size=size_val,
            preview_images=_parse_preview_images(preview_images),
            forum_name=forum_name,
            board_name=board_name,
            extract_password=extract_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()
