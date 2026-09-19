import httpx
import pytest

from app.main import create_admin_app, create_public_app
from app.libraries.models import LibraryRoot
from app.libraries.service import LibraryService
from app.settings import Settings
from tests.test_library_service import FakeFS


def _settings(tmp_path):
    return Settings(_env_file=None, data_dir=str(tmp_path))


class FailingFS(FakeFS):
    def __init__(self, failure="provider secret C:\\private"):
        super().__init__()
        self.failure = failure

    def drives(self):
        raise RuntimeError(self.failure)

    def directories(self, path):
        raise OSError(self.failure)

    def validate_directory(self, path):
        raise RuntimeError(self.failure)


class ValueFailFS(FakeFS):
    def drives(self):
        raise ValueError("provider secret C:\\private")


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
        assert "SameSite=strict" in session.headers["set-cookie"]
        reused = await client.get("/admin/api/session")
        assert reused.status_code == 200
        assert reused.json()["csrf_token"] == csrf
        assert "set-cookie" not in reused.headers
        assert (await client.get("/admin/api/filesystem/drives")).json() == {"drives": ["C:\\", "D:\\"]}
        assert (await client.get("/admin/api/filesystem/directories", params={"path": "C:\\"})).json() == {
            "directories": ["C:\\Pictures"]
        }
        assert (await client.post("/admin/api/filesystem/validate", json={"path": "C:\\Pictures"})).status_code == 403
        validated = await client.post(
            "/admin/api/filesystem/validate",
            json={"path": "C:\\Pictures"},
            headers={"X-CSRF-Token": csrf},
        )
        assert validated.status_code == 200
        assert validated.json() == {"valid": True, "path": "C:\\Pictures"}
        assert (await client.post("/admin/api/libraries", json={"name": "x", "path": "C:\\Pictures"})).status_code == 403
        assert (await client.patch("/admin/api/libraries/missing", json={"enabled": False})).status_code == 403
        assert (await client.delete("/admin/api/libraries/missing")).status_code == 403
        created = await client.post(
            "/admin/api/libraries",
            json={"name": "Pictures", "path": "C:\\Pictures", "recursive": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201
        library_id = created.json()["id"]
        duplicate = await client.post(
            "/admin/api/libraries",
            json={"name": "Pictures", "path": "C:\\Pictures"},
            headers={"X-CSRF-Token": csrf},
        )
        assert duplicate.status_code == 409
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


@pytest.mark.asyncio
async def test_admin_rejects_bearer_authorization_even_from_loopback(tmp_path):
    app = create_admin_app(_settings(tmp_path), filesystem=FakeFS())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        session = await client.get("/admin/api/session", headers={"Authorization": "Bearer local-token"})
        assert session.status_code == 403
        assert (await client.get("/admin/api/filesystem/drives", headers={"Authorization": "bearer local-token"})).status_code == 403
        clean_session = await client.get("/admin/api/session")
        mutation = await client.post(
            "/admin/api/libraries",
            json={"name": "Pictures", "path": "C:\\Pictures"},
            headers={
                "Authorization": "Bearer local-token",
                "X-CSRF-Token": clean_session.json()["csrf_token"],
            },
        )
        assert mutation.status_code == 403


@pytest.mark.asyncio
async def test_admin_translates_malformed_config_and_provider_failures(tmp_path):
    (tmp_path / "config.yaml").write_text("libraries: [", encoding="utf-8")
    app = create_admin_app(_settings(tmp_path), filesystem=FakeFS())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        malformed = await client.get("/admin/api/libraries")
        assert malformed.status_code == 422
        assert "config.yaml" not in malformed.text

    app = create_admin_app(_settings(tmp_path), filesystem=FailingFS())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        drives = await client.get("/admin/api/filesystem/drives")
        assert drives.status_code == 503
        assert "private" not in drives.text
        directories = await client.get("/admin/api/filesystem/directories", params={"path": "C:\\Pictures"})
        assert directories.status_code == 503
        session = await client.get("/admin/api/session")
        csrf = session.json()["csrf_token"]
        validate = await client.post(
            "/admin/api/filesystem/validate",
            json={"path": "C:\\Pictures"},
            headers={"X-CSRF-Token": csrf},
        )
        assert validate.status_code == 503

    (tmp_path / "config.yaml").write_text(
        "libraries:\n  - id: pictures\n    name: Pictures\n    path: C:\\\\Pictures\n",
        encoding="utf-8",
    )
    app = create_admin_app(_settings(tmp_path), filesystem=ValueFailFS())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        provider_value = await client.get("/admin/api/libraries")
        assert provider_value.status_code == 503


@pytest.mark.asyncio
async def test_admin_delete_translates_storage_failure_to_503(tmp_path):
    # Build a real configuration first, then exercise delete against a failing provider.
    library_service = LibraryService(tmp_path, filesystem=FakeFS())
    library_service.create(LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures"))
    app = create_admin_app(_settings(tmp_path), library_service=library_service)
    library_service.filesystem = FailingFS()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:3001") as client:
        session = await client.get("/admin/api/session")
        response = await client.delete(
            "/admin/api/libraries/pictures",
            headers={"X-CSRF-Token": session.json()["csrf_token"]},
        )
        assert response.status_code == 503
