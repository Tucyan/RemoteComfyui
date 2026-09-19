import httpx
import pytest

from app.main import create_public_app
from app.settings import Settings


@pytest.mark.asyncio
async def test_health_reports_gateway_and_comfyui_online():
    async def health_probe():
        return {"online": True, "version": "0.3.10"}

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {"status": "online", "version": "0.3.10", "error": None},
    }


@pytest.mark.asyncio
async def test_health_degrades_when_comfyui_is_unavailable():
    async def health_probe():
        raise ConnectionError("failed to read C:\\secrets\\comfyui-token.txt token=super-secret")

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {
            "status": "offline",
            "version": None,
            "error": "ComfyUI health check failed",
        },
    }

    assert "comfyui-token.txt" not in response.text
    assert "super-secret" not in response.text


@pytest.mark.asyncio
async def test_health_does_not_log_secret_bearing_probe_exception(caplog):
    async def health_probe():
        raise ConnectionError("failed to read C:\\secrets\\comfyui-token.txt token=super-secret")

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    with caplog.at_level("ERROR", logger="app.main"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert "ConnectionError" in caplog.text
    assert "comfyui-token.txt" not in caplog.text
    assert "super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_health_sanitizes_secret_bearing_probe_error():
    async def health_probe():
        return {"online": False, "error": "token=super-secret"}

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {
            "status": "offline",
            "version": None,
            "error": "ComfyUI health check failed",
        },
    }
    assert "super-secret" not in response.text


@pytest.mark.asyncio
async def test_health_suppresses_secret_bearing_online_error_and_invalid_version():
    async def health_probe():
        return {
            "online": True,
            "version": "token=super-secret",
            "error": "authorization=super-secret",
        }

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {"status": "online", "version": None, "error": None},
    }
    assert "super-secret" not in response.text


@pytest.mark.asyncio
async def test_health_omits_version_when_comfyui_is_offline():
    async def health_probe():
        return {"online": False, "version": "0.30.0"}

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {
            "status": "offline",
            "version": None,
            "error": "ComfyUI health check failed",
        },
    }


@pytest.mark.asyncio
async def test_health_preserves_valid_comfyui_semver_version():
    async def health_probe():
        return {"online": True, "version": "0.30.0"}

    app = create_public_app(Settings(_env_file=None), health_probe=health_probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "gateway": {"status": "online"},
        "comfyui": {"status": "online", "version": "0.30.0", "error": None},
    }
