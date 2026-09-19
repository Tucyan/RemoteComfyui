from __future__ import annotations

import ipaddress
import hashlib
import secrets
import time
from urllib.parse import urlparse

from fastapi import Request
from starlette.responses import JSONResponse

from .db import Database


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
    authorization = request.headers.get("authorization", "")
    if authorization.strip().lower().startswith("bearer "):
        raise PermissionError("bearer authorization is not accepted by the admin API")
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


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TokenService:
    def __init__(self, database: Database | str):
        self.db = database if isinstance(database, Database) else Database(database)

    def issue(self, device_name: str) -> str:
        if not isinstance(device_name, str) or not device_name.strip():
            raise ValueError("device name is required")
        raw = "rc_" + secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute(
            "INSERT INTO devices(id,name,token_hash,created_at) VALUES(?,?,?,?)",
            (secrets.token_hex(16), device_name.strip()[:120], _hash_token(raw), now),
        )
        return raw

    def verify(self, raw_token: str) -> dict[str, object]:
        if not isinstance(raw_token, str) or not raw_token.startswith("rc_"):
            raise PermissionError("invalid device token")
        row = self.db.fetchone(
            "SELECT id,name,created_at,last_seen_at,revoked_at FROM devices WHERE token_hash=?",
            (_hash_token(raw_token),),
        )
        if row is None or row["revoked_at"] is not None:
            raise PermissionError("invalid device token")
        self.db.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (time.time(), row["id"]))
        return {"id": row["id"], "name": row["name"], "device_name": row["name"], "created_at": row["created_at"]}


class PairingService(TokenService):
    def __init__(self, database: Database | str, *, pairing_ttl: int = 300):
        super().__init__(database)
        self.pairing_ttl = max(1, int(pairing_ttl))

    def create_pairing_code(self, *, now: float | None = None) -> str:
        current = time.time() if now is None else now
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.db.execute(
            "INSERT INTO pairings(id,code_hash,expires_at) VALUES(?,?,?)",
            (secrets.token_hex(16), _hash_token(code), current + self.pairing_ttl),
        )
        return code

    def redeem_pairing_code(self, code: str, device_name: str, *, now: float | None = None) -> str:
        current = time.time() if now is None else now
        if not isinstance(code, str) or not code.isdigit() or len(code) != 6:
            raise ValueError("invalid or expired pairing code")
        with self.db.transaction() as connection:
            row = connection.execute(
                "SELECT id,expires_at,used_at FROM pairings WHERE code_hash=?",
                (_hash_token(code),),
            ).fetchone()
            if row is None or row["used_at"] is not None or current >= row["expires_at"]:
                raise ValueError("invalid or expired pairing code")
            raw = "rc_" + secrets.token_urlsafe(32)
            connection.execute("UPDATE pairings SET used_at=? WHERE id=?", (current, row["id"]))
            connection.execute(
                "INSERT INTO devices(id,name,token_hash,created_at) VALUES(?,?,?,?)",
                (secrets.token_hex(16), device_name.strip()[:120], _hash_token(raw), current),
            )
        return raw

    def authenticate(self, raw_token: str) -> dict[str, object]:
        return self.verify(raw_token)

    def list_devices(self) -> list[dict[str, object]]:
        rows = self.db.fetchall("SELECT id,name,token_hash,created_at,last_seen_at,revoked_at FROM devices ORDER BY created_at DESC")
        return [dict(row) for row in rows]

    def revoke_device(self, device_id: str) -> None:
        if self.db.execute("UPDATE devices SET revoked_at=? WHERE id=?", (time.time(), device_id)) == 0:
            raise KeyError(device_id)
