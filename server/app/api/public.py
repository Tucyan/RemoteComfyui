from __future__ import annotations

import mimetypes
import hashlib
import secrets
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..jobs.service import JobService
from ..libraries.service import LibraryService
from ..security import PairingService
from ..settings import Settings


class PairRequest(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=120)


class ImageJobRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    prompt: str = Field(min_length=1, max_length=10000)
    reference_asset_ids: list[str] = Field(alias="referenceAssetIds", min_length=1, max_length=3)
    seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def non_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class VideoJobRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    prompt: str = Field(min_length=1, max_length=10000)
    reference_asset_ids: list[str] = Field(alias="referenceAssetIds", min_length=1, max_length=9)
    width: int = 1344
    height: int = 768
    frames: int = 124
    resolution_preset: str | None = Field(default=None, alias="resolutionPreset")
    seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def non_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


def register_public_routes(app, settings: Settings, pairing: PairingService, jobs: JobService, libraries: LibraryService) -> None:
    router = APIRouter(prefix="/api/v1")

    def device(request: Request) -> dict[str, object]:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="device authentication required", headers={"WWW-Authenticate": "Bearer"})
        try:
            return pairing.authenticate(token.strip())
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail="invalid device token", headers={"WWW-Authenticate": "Bearer"}) from exc

    @router.post("/pair")
    async def pair(payload: PairRequest):
        try:
            return {"token": pairing.redeem_pairing_code(payload.code, payload.name)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid or expired pairing code") from exc

    @router.post("/uploads/images")
    async def upload_images(request: Request, files: list[UploadFile] = File(...)):
        device(request)
        if not files or len(files) > 9:
            raise HTTPException(status_code=422, detail="one to nine images are allowed")
        upload_dir = Path(settings.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for upload in files:
            content_type = (upload.content_type or "").lower()
            suffix = Path(upload.filename or "").suffix.lower()
            if content_type not in {"image/png", "image/jpeg", "image/webp"} or suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise HTTPException(status_code=415, detail="only PNG, JPEG, and WebP images are allowed")
            content = await upload.read()
            if not content or len(content) > settings.max_upload_size_bytes:
                raise HTTPException(status_code=413, detail="image exceeds upload limit")
            asset_id = "asset_" + secrets.token_urlsafe(12)
            path = upload_dir / f"{asset_id}{suffix}"
            path.write_bytes(content)
            jobs.db.execute("INSERT INTO uploads(id,filename,storage_path,mime_type,size,created_at) VALUES(?,?,?,?,?,?)", (asset_id, Path(upload.filename or "image").name[:160], str(path), content_type, len(content), time.time()))
            results.append({"id": asset_id, "filename": Path(upload.filename or "image").name, "mime_type": content_type, "size": len(content)})
        return {"assets": results}

    async def create_job(request: Request, kind: str, payload: ImageJobRequest | VideoJobRequest):
        device(request)
        rows = []
        for asset_id in payload.reference_asset_ids:
            row = jobs.db.fetchone("SELECT * FROM uploads WHERE id=?", (asset_id,))
            if row is None:
                raise HTTPException(status_code=422, detail="unknown reference asset")
            rows.append(row)
        values = {"prompt": payload.prompt, "reference_images": [row["filename"] for row in rows], "reference_files": [{"asset_id": row["id"], "filename": row["filename"], "path": row["storage_path"], "mime_type": row["mime_type"]} for row in rows], "reference_asset_ids": payload.reference_asset_ids}
        try:
            if kind == "video":
                width, height = _video_dimensions(payload)
                values.update({"width": width, "height": height, "frames": payload.frames})
            if payload.seed is not None:
                values["seed"] = payload.seed
            # Workflow builders are the canonical validation boundary.
            if kind == "image":
                from ..comfy.workflows import build_qwen_prompt
                build_qwen_prompt(values["reference_images"], payload.prompt, seed=payload.seed)
            else:
                from ..comfy.workflows import build_minimax_prompt
                build_minimax_prompt(values["reference_images"], payload.prompt, width=values["width"], height=values["height"], frames=payload.frames, seed=payload.seed)
            created = jobs.create_job(kind, values)
            jobs.wake_worker()
            return _public_job(created)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/jobs/image", status_code=202)
    async def image_job(request: Request, payload: ImageJobRequest):
        return await create_job(request, "image", payload)

    @router.post("/jobs/video", status_code=202)
    async def video_job(request: Request, payload: VideoJobRequest):
        return await create_job(request, "video", payload)

    @router.get("/jobs")
    async def job_list(request: Request, limit: int = 50, status: str | None = None):
        device(request)
        try:
            return {"jobs": [_public_job(job) for job in jobs.list_jobs(limit=limit, status=status)]}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/jobs/{job_id}")
    async def job_detail(request: Request, job_id: str):
        device(request)
        try:
            return _public_job(jobs.get_job(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(request: Request, job_id: str):
        device(request)
        try:
            return _public_job(jobs.cancel(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @router.get("/artifacts")
    async def artifacts(request: Request):
        device(request)
        return {"artifacts": jobs.list_artifacts()}

    @router.get("/artifacts/{artifact_id}/content")
    async def artifact_content(request: Request, artifact_id: str):
        device(request)
        try:
            artifact = jobs.get_artifact(artifact_id)
            total = artifact["size"]
            range_header = request.headers.get("range")
            start, end, partial = 0, total - 1, False
            if range_header:
                start, end = _parse_range(range_header, total)
                partial = True
            content, _, mime = jobs.read_artifact(artifact_id, start, end)
            headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(content))}
            if partial:
                headers["Content-Range"] = f"bytes {start}-{end}/{total}"
            return Response(content, status_code=206 if partial else 200, media_type=mime, headers=headers)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=416, detail="invalid range") from exc

    @router.delete("/artifacts/{artifact_id}", status_code=204)
    async def delete_artifact(request: Request, artifact_id: str):
        device(request)
        try:
            jobs.delete_artifact(artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc

    @router.get("/libraries")
    async def library_list(request: Request):
        device(request)
        return {"libraries": [{"id": root.id, "name": root.name, "recursive": root.recursive} for root in libraries.load() if root.enabled]}

    @router.get("/libraries/{library_id}/images")
    async def library_images(request: Request, library_id: str, limit: int = 50, offset: int = 0, search: str = ""):
        device(request)
        root = next((item for item in libraries.load() if item.id == library_id and item.enabled), None)
        if root is None:
            raise HTTPException(status_code=404, detail="library not found")
        _sync_library(jobs, root)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        rows = jobs.db.fetchall(
            "SELECT id,relative_path,mime_type,size,mtime FROM library_images WHERE library_id=? AND relative_path LIKE ? ORDER BY mtime DESC LIMIT ? OFFSET ?",
            (library_id, f"%{search}%", limit, offset),
        )
        return {"images": [{"id": row["id"], "name": Path(row["relative_path"]).name, "relative_path": row["relative_path"], "mime_type": row["mime_type"], "size": row["size"], "mtime": row["mtime"], "thumbnail_url": f"/api/v1/library-images/{row['id']}/thumbnail", "content_url": f"/api/v1/library-images/{row['id']}/content"} for row in rows]}

    @router.get("/library-images/{image_id}/content")
    async def library_image_content(request: Request, image_id: str):
        device(request)
        row, path = _resolve_library_image(jobs, libraries, image_id)
        return Response(path.read_bytes(), media_type=row["mime_type"])

    @router.post("/library-images/{image_id}/import")
    async def import_library_image(request: Request, image_id: str):
        device(request)
        row, path = _resolve_library_image(jobs, libraries, image_id)
        size = path.stat().st_size
        if size < 1 or size > settings.max_upload_size_bytes:
            raise HTTPException(status_code=413, detail="image exceeds upload limit")
        asset_id = "asset_" + secrets.token_urlsafe(12)
        upload_dir = Path(settings.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{asset_id}{path.suffix.lower()}"
        shutil.copyfile(path, target)
        jobs.db.execute("INSERT INTO uploads(id,filename,storage_path,mime_type,size,created_at) VALUES(?,?,?,?,?,?)", (asset_id, path.name[:160], str(target), row["mime_type"], size, time.time()))
        return {"id": asset_id, "filename": path.name, "mime_type": row["mime_type"], "size": size}

    @router.get("/library-images/{image_id}/thumbnail")
    async def library_image_thumbnail(request: Request, image_id: str):
        return await library_image_content(request, image_id)

    app.include_router(router)


def _public_job(job: dict) -> dict:
    return {key: job.get(key) for key in ("id", "kind", "status", "prompt_id", "error", "created_at", "updated_at", "started_at", "artifacts")}


def _parse_range(value: str, total: int) -> tuple[int, int]:
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("invalid range")
    raw = value[6:].strip()
    left, separator, right = raw.partition("-")
    if not separator:
        raise ValueError("invalid range")
    if left:
        start = int(left)
        end = int(right) if right else total - 1
    else:
        length = int(right)
        if length <= 0:
            raise ValueError("invalid range")
        start, end = max(0, total - length), total - 1
    if start < 0 or start >= total or end < start:
        raise ValueError("invalid range")
    return start, min(end, total - 1)


_VIDEO_PRESETS = {
    "portrait_low": (352, 608),
    "landscape_low": (608, 352),
    "square_low": (448, 448),
    "portrait_standard": (480, 864),
    "landscape_standard": (864, 480),
    "square_standard": (640, 640),
}


def _video_dimensions(payload: VideoJobRequest) -> tuple[int, int]:
    if payload.resolution_preset:
        try:
            return _VIDEO_PRESETS[payload.resolution_preset]
        except KeyError as exc:
            raise ValueError("unsupported video resolution preset") from exc
    from ..comfy.workflows import validate_video_dimensions
    return validate_video_dimensions(payload.width, payload.height)


def _resolve_library_image(jobs: JobService, libraries: LibraryService, image_id: str):
    row = jobs.db.fetchone("SELECT * FROM library_images WHERE id=?", (image_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="library image not found")
    root = next((item for item in libraries.load() if item.id == row["library_id"] and item.enabled), None)
    if root is None:
        raise HTTPException(status_code=404, detail="library image not found")
    root_path = Path(root.path).resolve()
    path = Path(row["storage_path"]).resolve()
    if root_path not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="library image not found")
    return row, path


def _sync_library(jobs: JobService, root) -> None:
    root_path = Path(root.path).resolve()
    if not root_path.is_dir():
        return
    iterator = root_path.rglob("*") if root.recursive else root_path.glob("*")
    allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    for path in iterator:
        try:
            resolved = path.resolve()
            if not resolved.is_file() or root_path not in resolved.parents or resolved.suffix.lower() not in allowed:
                continue
            relative = resolved.relative_to(root_path).as_posix()
            stat = resolved.stat()
            image_id = "libimg_" + hashlib.sha256(f"{root.id}:{relative}".encode("utf-8")).hexdigest()[:24]
            jobs.db.execute(
                "INSERT INTO library_images(id,library_id,relative_path,storage_path,mime_type,size,mtime) VALUES(?,?,?,?,?,?,?) ON CONFLICT(library_id,relative_path) DO UPDATE SET storage_path=excluded.storage_path,mime_type=excluded.mime_type,size=excluded.size,mtime=excluded.mtime",
                (image_id, root.id, relative, str(resolved), allowed[resolved.suffix.lower()], stat.st_size, stat.st_mtime),
            )
        except OSError:
            continue
