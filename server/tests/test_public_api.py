from __future__ import annotations

import httpx
import pytest

from app.db import Database
from app.main import create_public_app
from app.security import PairingService


@pytest.mark.asyncio
async def test_public_api_requires_bearer_token_and_validates_generation_inputs(tmp_path):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path))
    pairing = PairingService(tmp_path / "gateway.db")
    code = pairing.create_pairing_code()
    token = pairing.redeem_pairing_code(code, "test-phone")
    app = create_public_app(settings, pairing_service=pairing)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/jobs")).status_code == 401
        headers = {"authorization": f"Bearer {token}"}
        invalid = await client.post("/api/v1/jobs/image", headers=headers, json={"prompt": "x", "referenceAssetIds": []})
        assert invalid.status_code == 422
        invalid_video = await client.post("/api/v1/jobs/video", headers=headers, json={"prompt": "x", "referenceAssetIds": ["a"], "width": 641, "height": 384, "frames": 124})
        assert invalid_video.status_code == 422


@pytest.mark.asyncio
async def test_pair_endpoint_returns_token_once_and_artifact_range_is_streamable(tmp_path):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path))
    pairing = PairingService(tmp_path / "gateway.db")
    code = pairing.create_pairing_code()
    app = create_public_app(settings, pairing_service=pairing)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        paired = await client.post("/api/v1/pair", json={"code": code, "name": "phone"})
        assert paired.status_code == 200
        payload = paired.json()
        assert payload["token"].startswith("rc_")
        job = app.state.job_service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
        artifact = app.state.job_service.add_artifact(job["id"], "image/png", b"abcdef", "result.png")
        result = await client.get(f"/api/v1/artifacts/{artifact['id']}/content", headers={"Range": "bytes=1-3", "Authorization": f"Bearer {payload['token']}"})
        assert result.status_code == 206
        assert result.content == b"bcd"
        assert "content-range" in result.headers
