from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GatewayHealth(BaseModel):
    status: Literal["online"] = "online"


class ComfyUIHealth(BaseModel):
    status: Literal["online", "offline"]
    version: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    gateway: GatewayHealth
    comfyui: ComfyUIHealth

