"""资源库备份 API：配置 / 状态 / 立即备份 / 导入。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth.deps import require_permission
from workers.backup import (
    is_backup_busy,
    load_backup_config,
    run_backup_once,
    save_backup_config,
)
from workers.backup_import import (
    get_import_progress,
    run_backup_import_background,
    try_begin_import_job,
)

log = logging.getLogger(__name__)

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
        raise HTTPException(status_code=409, detail="正在备份或导入，请稍候再试")
    result = await run_backup_once(trigger="manual")
    if result.get("skipped") and result.get("reason") == "busy":
        raise HTTPException(
            status_code=409,
            detail=str(result.get("error") or "正在备份中，请稍候再试"),
        )
    ok = bool(result.get("ok"))
    return {
        "message": "ok" if ok else "failed",
        "result": result,
        "ok": ok,
        "bytes": result.get("bytes") or 0,
        "error": result.get("error"),
        "file": result.get("file"),
    }


@router.get("/backup/import/status")
def get_backup_import_status(
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """导入进度（可离开数据管理页再回来继续看）。"""
    job = get_import_progress()
    return {
        "message": "success",
        "busy": is_backup_busy() or bool(job.get("active")),
        "import_job": job,
    }


@router.post("/backup/import")
async def post_backup_import(
    file: UploadFile = File(...),
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """上传备份后后台异步导入；立刻返回，进度见 GET /backup/import/status。

    边收边写磁盘，不全量进内存；后台 gzip 流式解析 + SQLite 中转后再入库。
    """
    import os
    import tempfile
    from pathlib import Path

    from workers.backup_import import (
        _MAX_UPLOAD_BYTES,
        _UPLOAD_CHUNK,
        _import_workdir,
        abort_import_job,
    )
    from workers.runner import _log_activity

    filename = (file.filename or "").strip() or "upload.sql.gz"
    _log_activity(f"资源库备份导入：已接到请求 · {filename}")

    if is_backup_busy():
        _log_activity("资源库备份导入：忙碌，已拒绝")
        raise HTTPException(status_code=409, detail="正在备份或导入，请稍候再试")
    lower = filename.lower()
    if not (
        lower.endswith(".sql.gz")
        or lower.endswith(".gz")
        or lower.endswith(".sql")
        or lower.endswith(".zip")
    ):
        _log_activity(f"资源库备份导入：格式不支持 · {filename}")
        raise HTTPException(
            status_code=400,
            detail="请上传 .sql.gz / .gz / .sql / .zip 格式的资源库备份",
        )

    job = try_begin_import_job(filename)
    if job is None:
        _log_activity("资源库备份导入：忙碌，已拒绝")
        raise HTTPException(status_code=409, detail="正在备份或导入，请稍候再试")

    _log_activity(f"资源库备份导入：正在落盘 · {filename}")
    suffix = ".sql.gz" if lower.endswith(".sql.gz") else (Path(filename).suffix or ".bin")
    fd, path_s = tempfile.mkstemp(
        prefix="backup-up-", suffix=suffix, dir=str(_import_workdir())
    )
    upload_path = Path(path_s)
    nbytes = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                nbytes += len(chunk)
                if nbytes > _MAX_UPLOAD_BYTES:
                    raise ValueError(
                        f"文件过大（上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）"
                    )
                out.write(chunk)
        if nbytes <= 0:
            raise ValueError("上传文件为空")
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        abort_import_job(message=str(exc))
        _log_activity(f"资源库备份导入：落盘失败 · {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _log_activity(f"资源库备份导入：已落盘 {nbytes} 字节 · 后台流式合并 · {filename}")

    async def _bg() -> None:
        try:
            await run_backup_import_background(
                path=upload_path,
                filename=filename,
                cleanup_upload=True,
            )
        except Exception:
            log.exception("backup import background crashed")
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass

    asyncio.create_task(_bg())
    return {
        "message": "started",
        "started": True,
        "ok": True,
        "filename": filename,
        "bytes": nbytes,
        "busy": True,
        "import_job": get_import_progress(),
    }
