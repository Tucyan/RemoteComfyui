from __future__ import annotations

from io import BytesIO
import mimetypes
import hashlib
import math
import secrets
import shutil
import time
import warnings
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    workflow: Literal["qwen_edit_2511", "qwen_image_2_1_8gb_edit", "qwen_image_2_1_8gb_t2i"] = "qwen_edit_2511"
    reference_asset_ids: list[str] = Field(alias="referenceAssetIds", min_length=0, max_length=10)
    edit_size_mode: Literal["scale", "dimensions"] | None = Field(default=None, alias="editSizeMode")
    scale_factor: float | None = Field(default=None, alias="scaleFactor", gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    seed: int | None = None

    @field_validator("scale_factor", mode="before")
    @classmethod
    def strict_scale_factor(cls, value):
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("scaleFactor must be a JSON number")
        if not math.isfinite(float(value)):
            raise ValueError("scaleFactor must be finite")
        return value

    @field_validator("width", "height", mode="before")
    @classmethod
    def strict_dimension(cls, value):
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("width and height must be JSON integers")
        return value

    @field_validator("prompt")
    @classmethod
    def non_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @model_validator(mode="after")
    def validate_workflow_parameters(self) -> "ImageJobRequest":
        count = len(self.reference_asset_ids)
        has_dimensions = self.width is not None or self.height is not None
        has_scale = self.edit_size_mode is not None or self.scale_factor is not None
        if self.workflow == "qwen_edit_2511":
            if not 1 <= count <= 3:
                raise ValueError("qwen_edit_2511 requires 1 to 3 reference images")
            if has_dimensions or has_scale:
                raise ValueError("legacy Qwen Edit does not accept size parameters")
            return self
        if self.workflow == "qwen_image_2_1_8gb_edit":
            if not 1 <= count <= 10:
                raise ValueError("qwen_image_2_1_8gb_edit requires 1 to 10 reference images")
            if self.edit_size_mode == "scale":
                if self.scale_factor is None:
                    raise ValueError("scaleFactor is required in scale mode")
                if not 0.5 <= self.scale_factor <= 2.0:
                    raise ValueError("scaleFactor must be between 0.5 and 2.0")
                if has_dimensions:
                    raise ValueError("width and height are not accepted in scale mode")
            elif self.edit_size_mode == "dimensions":
                if self.width is None or self.height is None:
                    raise ValueError("width and height are required in dimensions mode")
                if self.scale_factor is not None:
                    raise ValueError("scaleFactor is not accepted in dimensions mode")
            else:
                raise ValueError("editSizeMode must be scale or dimensions")
            return self
        if count != 0:
            raise ValueError("qwen_image_2_1_8gb_t2i requires zero reference images")
        if self.width is None or self.height is None:
            raise ValueError("width and height are required for qwen_image_2_1_8gb_t2i")
        if has_scale:
            raise ValueError("edit size parameters are not accepted for qwen_image_2_1_8gb_t2i")
        return self


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
        if not files or len(files) > 10:
            raise HTTPException(status_code=422, detail="one to ten images are allowed")
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
            try:
                width, height = _image_dimensions(content)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            asset_id = "asset_" + secrets.token_urlsafe(12)
            path = upload_dir / f"{asset_id}{suffix}"
            path.write_bytes(content)
            jobs.db.execute("INSERT INTO uploads(id,filename,storage_path,mime_type,size,created_at) VALUES(?,?,?,?,?,?)", (asset_id, Path(upload.filename or "image").name[:160], str(path), content_type, len(content), time.time()))
            results.append({"id": asset_id, "filename": Path(upload.filename or "image").name, "mime_type": content_type, "size": len(content), "width": width, "height": height})
        return {"assets": results}

    async def create_job(request: Request, kind: str, payload: ImageJobRequest | VideoJobRequest):
        device(request)
        rows = []
        for asset_id in payload.reference_asset_ids:
            row = jobs.db.fetchone("SELECT * FROM uploads WHERE id=?", (asset_id,))
            if row is None:
                raise HTTPException(status_code=422, detail="unknown reference asset")
            rows.append(row)
        workflow = payload.workflow if kind == "image" else "minimax_h3"
        values = {"prompt": payload.prompt, "workflow": workflow, "reference_images": [row["filename"] for row in rows], "reference_files": [{"asset_id": row["id"], "filename": row["filename"], "path": row["storage_path"], "mime_type": row["mime_type"]} for row in rows], "reference_asset_ids": payload.reference_asset_ids}
        try:
            if kind == "video":
                width, height = _video_dimensions(payload)
                values.update({"width": width, "height": height, "frames": payload.frames})
            if payload.seed is not None:
                values["seed"] = payload.seed
            # Workflow builders are the canonical validation boundary.
            if kind == "image":
                _apply_image_workflow_values(values, payload, rows)
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
        try:
            width, height = _image_dimensions(path.read_bytes())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        asset_id = "asset_" + secrets.token_urlsafe(12)
        upload_dir = Path(settings.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{asset_id}{path.suffix.lower()}"
        shutil.copyfile(path, target)
        jobs.db.execute("INSERT INTO uploads(id,filename,storage_path,mime_type,size,created_at) VALUES(?,?,?,?,?,?)", (asset_id, path.name[:160], str(target), row["mime_type"], size, time.time()))
        return {"id": asset_id, "filename": path.name, "mime_type": row["mime_type"], "size": size, "width": width, "height": height}

    @router.get("/library-images/{image_id}/thumbnail")
    async def library_image_thumbnail(request: Request, image_id: str):
        return await library_image_content(request, image_id)

    app.include_router(router)


def _public_job(job: dict) -> dict:
    result = {key: job.get(key) for key in ("id", "kind", "status", "prompt_id", "error", "created_at", "updated_at", "started_at", "artifacts")}
    payload = job.get("payload") or {}
    result["workflow"] = payload.get("workflow") or ("qwen_edit_2511" if job.get("kind") == "image" else "minimax_h3")
    return result


def _image_dimensions(content: bytes) -> tuple[int, int]:
    """Read oriented dimensions from image metadata without decoding pixels."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("only PNG, JPEG, and WebP images are allowed")
                width, height = image.size
                image.verify()
            with Image.open(BytesIO(content)) as image:
                orientation = image.getexif().get(274, 1)
                if orientation in {5, 6, 7, 8}:
                    width, height = height, width
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("image dimensions exceed safety limit") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid image data") from exc
    if width < 1 or height < 1:
        raise ValueError("invalid image dimensions")
    return int(width), int(height)


def _align_dimension(value: float, multiple: int) -> int:
    return max(multiple, math.floor(value / multiple + 0.5) * multiple)


def _apply_image_workflow_values(values: dict, payload: ImageJobRequest, rows: list) -> None:
    from ..comfy.workflows import (
        build_qwen_21_edit_prompt,
        build_qwen_21_t2i_prompt,
        build_qwen_prompt,
    )

    if payload.workflow == "qwen_edit_2511":
        build_qwen_prompt(values["reference_images"], payload.prompt, seed=payload.seed)
        return
    if payload.workflow == "qwen_image_2_1_8gb_t2i":
        assert payload.width is not None and payload.height is not None
        if payload.width > 2048 or payload.height > 2048:
            raise ValueError("Qwen Image 2.1 dimensions must be at most 2048 pixels")
        if payload.width % 8 or payload.height % 8:
            raise ValueError("Qwen Image 2.1 T2I dimensions must be multiples of 8")
        values.update({"width": payload.width, "height": payload.height})
        build_qwen_21_t2i_prompt(payload.prompt, payload.width, payload.height, seed=payload.seed)
        return

    source_path = Path(rows[0]["storage_path"])
    try:
        source_width, source_height = _image_dimensions(source_path.read_bytes())
    except OSError as exc:
        raise ValueError("reference image is unavailable") from exc
    if payload.edit_size_mode == "scale":
        assert payload.scale_factor is not None
        requested_width = source_width * payload.scale_factor
        requested_height = source_height * payload.scale_factor
    else:
        assert payload.width is not None and payload.height is not None
        requested_width = payload.width
        requested_height = payload.height
        if requested_width > 2048 or requested_height > 2048:
            raise ValueError("Qwen Image 2.1 dimensions must be at most 2048 pixels")

    width = _align_dimension(requested_width, 32)
    height = _align_dimension(requested_height, 32)
    if payload.edit_size_mode == "dimensions":
        expected_height = _align_dimension(payload.width * source_height / source_width, 32)  # type: ignore[operator]
        if height != expected_height:
            raise ValueError("dimensions must preserve the first reference image aspect ratio")
    if width > 2048 or height > 2048:
        raise ValueError("Qwen Image 2.1 dimensions must be at most 2048 pixels")
    values.update({"width": width, "height": height, "edit_size_mode": payload.edit_size_mode})
    if payload.scale_factor is not None:
        values["scale_factor"] = payload.scale_factor
    build_qwen_21_edit_prompt(values["reference_images"], payload.prompt, width, height, seed=payload.seed)


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
