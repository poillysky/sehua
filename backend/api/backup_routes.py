"""资源库备份 API：配置 / 状态 / 立即备份 / 导入。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth.deps import require_permission
from workers.backup import (
    is_backup_busy,
    load_backup_config,
    run_backup_once,
    save_backup_config,
)
from workers.backup_import import run_backup_import

router = APIRouter(prefix="/api/system", tags=["backup"])


class BackupConfigBody(BaseModel):
    enabled: bool | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)


@router.get("/backup")
def get_backup(_user: dict = Depends(require_permission("settings.write"))) -> dict:
    cfg = load_backup_config()
    return {"message": "success", **cfg}


@router.put("/backup")
def put_backup(
    body: BackupConfigBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    if body.enabled is None and body.hour is None and body.minute is None:
        raise HTTPException(status_code=400, detail="请至少提供 enabled / hour / minute 之一")
    cfg = save_backup_config(enabled=body.enabled, hour=body.hour, minute=body.minute)
    return {"message": "success", **cfg}


@router.post("/backup/run")
async def post_backup_run(_user: dict = Depends(require_permission("settings.write"))) -> dict:
    if is_backup_busy():
        raise HTTPException(status_code=409, detail="备份正在进行中，请稍候")
    result = await run_backup_once(trigger="manual")
    if result.get("skipped") and result.get("reason") == "busy":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "备份忙碌"))
    ok = bool(result.get("ok"))
    return {
        "message": "ok" if ok else "failed",
        "result": result,
        "ok": ok,
        "bytes": result.get("bytes") or 0,
        "error": result.get("error"),
        "file": result.get("file"),
    }


@router.post("/backup/import")
async def post_backup_import(
    file: UploadFile = File(...),
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """上传备份压缩包（.sql.gz / .zip）合并导入；按资源 hash、标签名去重。"""
    if is_backup_busy():
        raise HTTPException(status_code=409, detail="备份或导入正在进行中，请稍候")
    filename = (file.filename or "").strip() or "upload.sql.gz"
    lower = filename.lower()
    if not (
        lower.endswith(".sql.gz")
        or lower.endswith(".gz")
        or lower.endswith(".sql")
        or lower.endswith(".zip")
    ):
        raise HTTPException(
            status_code=400,
            detail="请上传 .sql.gz / .gz / .sql / .zip 格式的资源库备份",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")

    result = await run_backup_import(raw=raw, filename=filename)
    if result.get("skipped") and result.get("reason") == "busy":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "导入忙碌"))
    ok = bool(result.get("ok"))
    return {
        "message": "ok" if ok else "failed",
        "ok": ok,
        "error": result.get("error"),
        "result": result,
        "resources_inserted": result.get("resources_inserted") or 0,
        "resources_updated": result.get("resources_updated") or 0,
        "resources_skipped": result.get("resources_skipped") or 0,
        "tags_upserted": result.get("tags_upserted") or 0,
        "resource_tags_linked": result.get("resource_tags_linked") or 0,
    }
