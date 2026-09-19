from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from fastapi import FastAPI

from .schemas import ComfyUIHealth, GatewayHealth, HealthResponse
from .settings import Settings

HealthProbe = Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]


async def _default_health_probe(settings: Settings) -> Mapping[str, Any]:
    async with httpx.AsyncClient(base_url=settings.comfyui_url, timeout=2.0) as client:
        response = await client.get("/system_stats")
        response.raise_for_status()
        payload = response.json()
    version = payload.get("system", {}).get("comfyui_version")
    return {"online": True, "version": version}


def _build_app(settings: Settings, health_probe: HealthProbe | None) -> FastAPI:
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
                    version=result.get("version"),
                    error=result.get("error"),
                ),
            )
        except Exception as exc:
            return HealthResponse(
                gateway=GatewayHealth(),
                comfyui=ComfyUIHealth(status="offline", error=str(exc)),
            )

    return app


def create_public_app(
    settings: Settings | None = None,
    health_probe: HealthProbe | None = None,
) -> FastAPI:
    return _build_app(settings or Settings(), health_probe)


def create_admin_app(settings: Settings | None = None) -> FastAPI:
    return _build_app(settings or Settings(), None)

