from __future__ import annotations

import inspect
import logging
import re
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from .api.admin import register_admin_routes
from .api.public import register_public_routes
from .comfy.client import ComfyUIClient
from .db import Database
from .jobs.service import JobService
from .libraries.service import LibraryService
from .security import PairingService, install_admin_guard
from .schemas import ComfyUIHealth, GatewayHealth, HealthResponse
from .settings import Settings

HealthProbe = Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
logger = logging.getLogger(__name__)
_SAFE_COMFYUI_VERSION = re.compile(
    r"(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})"
)


def _safe_comfyui_version(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 32:
        return None
    return value if _SAFE_COMFYUI_VERSION.fullmatch(value) else None


async def _default_health_probe(settings: Settings) -> Mapping[str, Any]:
    async with httpx.AsyncClient(base_url=settings.comfyui_url, timeout=2.0) as client:
        response = await client.get("/system_stats")
        response.raise_for_status()
        payload = response.json()
    version = payload.get("system", {}).get("comfyui_version")
    return {"online": True, "version": version}


def _default_admin_static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "apps" / "windows-admin" / "dist"


def _install_admin_ui(app: FastAPI, static_dir: str | Path | None) -> None:
    root = (Path(static_dir) if static_dir is not None else _default_admin_static_dir()).resolve()
    index = root / "index.html"

    def render_index() -> FileResponse | HTMLResponse:
        if not index.is_file():
            return HTMLResponse(
                "Admin UI build not found. Run npm run build in apps/windows-admin.",
                status_code=503,
            )
        return FileResponse(index)

    @app.get("/admin", include_in_schema=False)
    async def admin_root():
        return render_index()

    @app.get("/admin/{path:path}", include_in_schema=False)
    async def admin_spa(path: str):
        if path == "api" or path.startswith("api/"):
            return HTMLResponse("Not Found", status_code=404)
        requested = root / path
        if requested.is_file() and root in requested.resolve().parents:
            return FileResponse(requested)
        if path.startswith("assets/") or path == "favicon.ico":
            return HTMLResponse("Not Found", status_code=404)
        return render_index()


def _build_app(settings: Settings, health_probe: HealthProbe | None, *, admin: bool = False, filesystem=None, library_service=None, static_dir: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Remote ComfyUI Gateway")
    probe = health_probe or (lambda: _default_health_probe(settings))

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        try:
            result = probe()
            if inspect.isawaitable(result):
                result = await result
            online = bool(result.get("online", False))
            return HealthResponse(
                gateway=GatewayHealth(),
                comfyui=ComfyUIHealth(
                    status="online" if online else "offline",
                    version=_safe_comfyui_version(result.get("version")) if online else None,
                    error=None if online else "ComfyUI health check failed",
                ),
            )
        except Exception as exc:
            logger.error("ComfyUI health probe failed (%s)", type(exc).__name__)
            return HealthResponse(
                gateway=GatewayHealth(),
                comfyui=ComfyUIHealth(status="offline", error="ComfyUI health check failed"),
            )

    if admin:
        app.state.admin_sessions = {}
        install_admin_guard(app)
        pairing_factory = lambda: PairingService(Database(Path(settings.data_dir) / "remote-comfyui.db"))
        register_admin_routes(app, library_service or LibraryService(settings.data_dir, filesystem=filesystem), pairing_factory)
        _install_admin_ui(app, static_dir)

    return app


def create_public_app(
    settings: Settings | None = None,
    health_probe: HealthProbe | None = None,
    *,
    pairing_service: PairingService | None = None,
    job_service: JobService | None = None,
    comfy_client=None,
    library_service: LibraryService | None = None,
) -> FastAPI:
    runtime = settings or Settings()
    app = _build_app(runtime, health_probe)
    database = job_service.db if job_service is not None else Database(Path(runtime.data_dir) / "remote-comfyui.db")
    pairing = pairing_service or PairingService(database)
    comfy = comfy_client or ComfyUIClient(runtime.comfyui_url)
    jobs = job_service or JobService(database, comfy, runtime.data_dir)
    libraries = library_service or LibraryService(runtime.data_dir)
    app.state.pairing_service = pairing
    app.state.job_service = jobs
    app.state.library_service = libraries
    register_public_routes(app, runtime, pairing, jobs, libraries)

    parent_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with parent_lifespan(application):
            jobs.start_worker()
            try:
                yield
            finally:
                await jobs.stop_worker()

    app.router.lifespan_context = lifespan

    return app


def create_admin_app(settings: Settings | None = None, *, filesystem=None, library_service=None, static_dir: str | Path | None = None) -> FastAPI:
    return _build_app(settings or Settings(), None, admin=True, filesystem=filesystem, library_service=library_service, static_dir=static_dir)
