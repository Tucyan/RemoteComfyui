from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    """Runtime configuration for the gateway and its two HTTP listeners."""

    model_config = SettingsConfigDict(
        env_prefix="REMOTE_COMFYUI_",
        env_file=".env",
        extra="ignore",
    )

    comfyui_url: str = "http://127.0.0.1:8188"
    public_host: str = "0.0.0.0"
    public_port: int = 3000
    admin_host: str = "127.0.0.1"
    admin_port: int = 3001
    data_dir: str = "./data"
    max_upload_size_bytes: int = 100 * 1024 * 1024
    libraries: list[str] = []

    @field_validator("comfyui_url")
    @classmethod
    def validate_comfyui_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("comfyui_url must be an HTTP(S) URL")
        if not _is_loopback_host(parsed.hostname):
            raise ValueError("comfyui_url must target a loopback host")
        return value.rstrip("/")

    @field_validator("admin_host")
    @classmethod
    def validate_admin_host(cls, value: str) -> str:
        if not _is_loopback_host(value):
            raise ValueError("admin_host must be a loopback host")
        return value

    @field_validator("public_port", "admin_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator("max_upload_size_bytes")
    @classmethod
    def validate_upload_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_upload_size_bytes must be positive")
        return value

