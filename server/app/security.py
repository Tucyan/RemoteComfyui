from __future__ import annotations

import ipaddress
import secrets
from urllib.parse import urlparse

from fastapi import Request
from starlette.responses import JSONResponse


def _loopback(value: str | None) -> bool:
    if not value:
        return False
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def enforce_admin_request(request: Request) -> None:
    client_host = request.client.host if request.client else None
    if not _loopback(client_host):
        raise PermissionError("admin API requires a loopback client")
    host_header = request.headers.get("host", "")
    if host_header.startswith("["):
        host = host_header.partition("]")[0].lstrip("[")
    else:
        host = host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header
    host = host.strip("[]")
    if not _loopback(host):
        raise PermissionError("admin API requires a loopback Host")
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlparse(origin)
            default_port = 443 if request.url.scheme == "https" else 80
            origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            request_port = request.url.port or default_port
        except ValueError as exc:
            raise PermissionError("cross-origin admin requests are not allowed") from exc
        if parsed.scheme != request.url.scheme or parsed.hostname != host or origin_port != request_port:
            raise PermissionError("cross-origin admin requests are not allowed")


def get_or_create_session(request: Request) -> tuple[str, str, bool]:
    sessions = request.app.state.admin_sessions
    session_id = request.cookies.get("admin_session")
    if session_id not in sessions:
        session_id = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        sessions[session_id] = csrf
        return session_id, csrf, True
    return session_id, sessions[session_id], False


def require_csrf(request: Request) -> None:
    session_id = request.cookies.get("admin_session")
    expected = request.app.state.admin_sessions.get(session_id)
    supplied = request.headers.get("x-csrf-token")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")


def install_admin_guard(app) -> None:
    @app.middleware("http")
    async def admin_guard(request: Request, call_next):
        try:
            enforce_admin_request(request)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=403)
        return await call_next(request)
