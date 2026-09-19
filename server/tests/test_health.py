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
