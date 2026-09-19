import httpx
import pytest

from app.main import create_admin_app, create_public_app
from app.settings import Settings
from tests.test_library_service import FakeFS


def _settings(tmp_path):
    return Settings(_env_file=None, data_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_public_app_does_not_expose_admin_routes(tmp_path):
    app = create_public_app(_settings(tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:3000") as client:
        assert (await client.get("/admin/api/session")).status_code == 404


@pytest.mark.asyncio
async def test_admin_session_and_library_mutations_require_csrf_and_loopback(tmp_path):
    app = create_admin_app(_settings(tmp_path), filesystem=FakeFS())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        session = await client.get("/admin/api/session")
        assert session.status_code == 200
        csrf = session.json()["csrf_token"]
        assert "HttpOnly" in session.headers["set-cookie"]
        assert (await client.post("/admin/api/libraries", json={"name": "x", "path": "C:\\Pictures"})).status_code == 403
        created = await client.post(
            "/admin/api/libraries",
            json={"name": "Pictures", "path": "C:\\Pictures", "recursive": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201
        library_id = created.json()["id"]
        changed = await client.patch(
            f"/admin/api/libraries/{library_id}",
            json={"enabled": False},
            headers={"X-CSRF-Token": csrf},
        )
        assert changed.status_code == 200
        assert changed.json()["enabled"] is False
        deleted = await client.delete(f"/admin/api/libraries/{library_id}", headers={"X-CSRF-Token": csrf})
        assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_admin_rejects_bad_host_and_origin(tmp_path):
    app = create_admin_app(_settings(tmp_path), filesystem=FakeFS())
    transport = httpx.ASGITransport(app=app, client=("192.168.1.20", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        assert (await client.get("/admin/api/session")).status_code == 403
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        assert (await client.get("/admin/api/session", headers={"Origin": "http://evil.test"})).status_code == 403
