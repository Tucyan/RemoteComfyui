from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx


class ComfyUIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class ComfyUIClient:
    """Small async adapter for the local ComfyUI HTTP API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188", *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30.0):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not _is_loopback(parsed.hostname):
            raise ValueError("ComfyUI client requires a loopback URL")
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, transport=self._transport, timeout=self._timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ComfyUIError("ComfyUI is unavailable") from exc
        if response.status_code >= 400:
            raise ComfyUIError("ComfyUI request failed", response.status_code)
        return response

    async def upload_image(self, filename: str, content: bytes, *, content_type: str = "application/octet-stream", image_type: str = "input", overwrite: bool = False) -> dict[str, Any]:
        if not filename or "\x00" in filename or ".." in filename.replace("\\", "/").split("/"):
            raise ValueError("invalid upload filename")
        response = await self._request(
            "POST",
            "/upload/image",
            data={"type": image_type, "overwrite": str(overwrite).lower()},
            files={"image": (filename, content, content_type)},
        )
        return self._json(response)

    async def queue_prompt(self, prompt: Mapping[str, Any], *, client_id: str | None = None) -> dict[str, Any]:
        if not isinstance(prompt, Mapping) or not prompt:
            raise ValueError("prompt must be a non-empty mapping")
        payload: dict[str, Any] = {"prompt": dict(prompt)}
        if client_id is not None:
            payload["client_id"] = client_id
        response = await self._request("POST", "/prompt", json=payload)
        return self._json(response)

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        return self._json(await self._request("GET", f"/history/{self._safe_id(prompt_id)}"))

    async def get_queue(self) -> dict[str, Any]:
        return self._json(await self._request("GET", "/queue"))

    async def view(self, filename: str, *, subfolder: str = "", folder_type: str = "output") -> bytes:
        if not filename or "\x00" in filename or ".." in filename.replace("\\", "/").split("/"):
            raise ValueError("invalid view filename")
        response = await self._request("GET", "/view", params={"filename": filename, "subfolder": subfolder, "type": folder_type})
        return response.content

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or "/" in value or "\\" in value or ".." in value:
            raise ValueError("invalid prompt id")
        return value

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ComfyUIError("ComfyUI returned invalid JSON", response.status_code) from exc
        if not isinstance(payload, dict):
            raise ComfyUIError("ComfyUI returned an invalid response", response.status_code)
        return payload


__all__ = ["ComfyUIClient", "ComfyUIError"]
