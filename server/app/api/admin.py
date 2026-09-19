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
        try:
            return {"drives": service.list_drives()}
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.get("/filesystem/directories")
    async def directories(request: Request, path: str | None = None):
        try:
            return {"directories": service.list_directories(path)}
        except PathValidationError as exc:
            raise _bad_path() from exc
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.post("/filesystem/validate")
    async def validate(request: Request, payload: PathPayload):
        require_csrf(request)
        try:
            path = service.validate_path(payload.path)
            return {"valid": True, "path": path}
        except (PathValidationError, AttributeError, TypeError) as exc:
            raise _bad_path() from exc
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.get("/libraries")
    async def libraries():
        try:
            return {"libraries": [item.to_dict() for item in service.load()]}
        except ValueError as exc:
            raise _invalid_config() from exc
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.post("/libraries", status_code=201)
    async def create_library(request: Request, payload: LibraryCreate):
        require_csrf(request)
        library_id = payload.id or _slugify(payload.name)
        try:
            item = service.create(LibraryRoot(id=library_id, name=payload.name.strip(), path=payload.path, recursive=payload.recursive, enabled=payload.enabled))
            return item.to_dict()
        except PathValidationError as exc:
            raise _bad_path() from exc
        except ValueError as exc:
            if str(exc) == "invalid library configuration":
                raise _invalid_config() from exc
            if str(exc) == "library id already exists":
                raise HTTPException(status_code=409, detail="library id already exists") from exc
            raise HTTPException(status_code=400, detail="invalid library data") from exc
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.patch("/libraries/{library_id}")
    async def patch_library(library_id: str, request: Request, payload: LibraryPatch):
        require_csrf(request)
        changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
        try:
            return service.update(library_id, **changes).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="library not found") from exc
        except PathValidationError as exc:
            raise _bad_path() from exc
        except ValueError as exc:
            if str(exc) == "invalid library configuration":
                raise _invalid_config() from exc
            if str(exc) == "library id already exists":
                raise HTTPException(status_code=409, detail="library id already exists") from exc
            raise HTTPException(status_code=400, detail="invalid library data") from exc
        except Exception as exc:
            raise _service_unavailable() from exc

    @router.delete("/libraries/{library_id}", status_code=204)
    async def delete_library(library_id: str, request: Request):
        require_csrf(request)
        try:
            service.delete(library_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="library not found") from exc
        except PathValidationError as exc:
            raise _bad_path() from exc
        except ValueError as exc:
            raise _invalid_config() from exc
        except Exception as exc:
            raise _service_unavailable() from exc
        return Response(status_code=204)

    app.include_router(router)


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "library"


def _bad_path() -> HTTPException:
    return HTTPException(status_code=400, detail="invalid or inaccessible directory path")


def _invalid_config() -> HTTPException:
    return HTTPException(status_code=422, detail="invalid library configuration")


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="library storage/provider unavailable")
