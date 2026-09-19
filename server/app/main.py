from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from fastapi import FastAPI

from .api.admin import register_admin_routes
from .libraries.service import LibraryService
from .security import install_admin_guard
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


def _build_app(settings: Settings, health_probe: HealthProbe | None, *, admin: bool = False, filesystem=None, library_service=None) -> FastAPI:
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
        register_admin_routes(app, library_service or LibraryService(settings.data_dir, filesystem=filesystem))

    return app


def create_public_app(
    settings: Settings | None = None,
    health_probe: HealthProbe | None = None,
) -> FastAPI:
    return _build_app(settings or Settings(), health_probe)


def create_admin_app(settings: Settings | None = None, *, filesystem=None, library_service=None) -> FastAPI:
    return _build_app(settings or Settings(), None, admin=True, filesystem=filesystem, library_service=library_service)
