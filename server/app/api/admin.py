from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..libraries.models import LibraryRoot
from ..libraries.service import LibraryService, PathValidationError
from ..security import get_or_create_session, require_csrf


class LibraryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    name: str = Field(min_length=1)
    path: str
    recursive: bool = True
    enabled: bool = True


class LibraryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1)
    path: str | None = None
    recursive: bool | None = None
    enabled: bool | None = None


class PathPayload(BaseModel):
    path: str


def register_admin_routes(app, service: LibraryService) -> None:
    router = APIRouter(prefix="/admin/api")

    @router.get("/session")
    async def session(request: Request, response: Response):
        session_id, csrf, fresh = get_or_create_session(request)
        if fresh:
            response.set_cookie("admin_session", session_id, httponly=True, samesite="strict", secure=False, path="/")
        return {"csrf_token": csrf}

    @router.get("/filesystem/drives")
    async def drives():
        return {"drives": service.list_drives()}

    @router.get("/filesystem/directories")
    async def directories(request: Request, path: str | None = None):
        try:
            return {"directories": service.list_directories(path)}
        except PathValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/filesystem/validate")
    async def validate(request: Request, payload: PathPayload):
        require_csrf(request)
        try:
            path = service.validate_path(payload.path)
            return {"valid": True, "path": path}
        except (PathValidationError, AttributeError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/libraries")
    async def libraries():
        return {"libraries": [item.to_dict() for item in service.load()]}

    @router.post("/libraries", status_code=201)
    async def create_library(request: Request, payload: LibraryCreate):
        require_csrf(request)
        library_id = payload.id or _slugify(payload.name)
        try:
            item = service.create(LibraryRoot(id=library_id, name=payload.name.strip(), path=payload.path, recursive=payload.recursive, enabled=payload.enabled))
            return item.to_dict()
        except (PathValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/libraries/{library_id}")
    async def patch_library(library_id: str, request: Request, payload: LibraryPatch):
        require_csrf(request)
        changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
        try:
            return service.update(library_id, **changes).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="library not found") from exc
        except (PathValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/libraries/{library_id}", status_code=204)
    async def delete_library(library_id: str, request: Request):
        require_csrf(request)
        try:
            service.delete(library_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="library not found") from exc
        return Response(status_code=204)

    app.include_router(router)


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "library"
