from __future__ import annotations

import httpx
import pytest
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_artifact_delete_requires_token_and_removes_computer_file(tmp_path):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path))
    pairing = PairingService(tmp_path / "gateway.db")
    token = pairing.redeem_pairing_code(pairing.create_pairing_code(), "phone")
    app = create_public_app(settings, pairing_service=pairing)
    job = app.state.job_service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    artifact = app.state.job_service.add_artifact(job["id"], "image/png", b"image", "result.png")
    path = __import__("pathlib").Path(app.state.job_service.db.fetchone("SELECT storage_path FROM artifacts WHERE id=?", (artifact["id"],))["storage_path"])
    url = f"/api/v1/artifacts/{artifact['id']}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.delete(url)).status_code == 401
        assert (await client.delete(url, headers={"Authorization": f"Bearer {token}"})).status_code == 204
        assert not path.exists()
        assert (await client.get(url + "/content", headers={"Authorization": f"Bearer {token}"})).status_code == 404
        assert (await client.delete(url, headers={"Authorization": f"Bearer {token}"})).status_code == 404


@pytest.mark.asyncio
async def test_library_image_can_be_imported_as_reference_without_phone_reupload(tmp_path):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    pairing = PairingService(tmp_path / "pairing.db")
    token = pairing.redeem_pairing_code(pairing.create_pairing_code(), "phone")
    source = tmp_path / "gallery"
    source.mkdir()
    (source / "sample.png").write_bytes(b"PNG image")
    libraries = SimpleNamespace(load=lambda: [SimpleNamespace(id="gallery", name="Gallery", path=str(source), enabled=True, recursive=True)])
    app = create_public_app(settings, pairing_service=pairing, library_service=libraries)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/libraries/gallery/images", headers=headers)
        image_id = listing.json()["images"][0]["id"]
        imported = await client.post(f"/api/v1/library-images/{image_id}/import", headers=headers)
        assert imported.status_code == 200
        asset_id = imported.json()["id"]
        assert app.state.job_service.db.fetchone("SELECT id FROM uploads WHERE id=?", (asset_id,)) is not None
        assert (source / "sample.png").read_bytes() == b"PNG image"
