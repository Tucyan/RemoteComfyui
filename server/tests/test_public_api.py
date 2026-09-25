from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image, ImageOps
import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from app.db import Database
from app.api.public import ImageJobRequest, _image_dimensions
from app.main import create_public_app
from app.security import PairingService


def _image_bytes(format_name: str = "PNG", size: tuple[int, int] = (4, 3), orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, (24, 96, 180))
    output = BytesIO()
    save_kwargs = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        save_kwargs["exif"] = exif
    image.save(output, format=format_name, **save_kwargs)
    return output.getvalue()


def _paired_app(tmp_path, *, library_service=None):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path))
    pairing = PairingService(tmp_path / "gateway.db")
    token = pairing.redeem_pairing_code(pairing.create_pairing_code(), "test-phone")
    app = create_public_app(settings, pairing_service=pairing, library_service=library_service)
    return app, {"Authorization": f"Bearer {token}"}


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
    source_bytes = _image_bytes("PNG", (7, 5))
    (source / "sample.png").write_bytes(source_bytes)
    libraries = SimpleNamespace(load=lambda: [SimpleNamespace(id="gallery", name="Gallery", path=str(source), enabled=True, recursive=True)])
    app = create_public_app(settings, pairing_service=pairing, library_service=libraries)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/libraries/gallery/images", headers=headers)
        image_id = listing.json()["images"][0]["id"]
        content_url = listing.json()["images"][0]["content_url"]
        assert (await client.get(content_url)).status_code == 401
        original = await client.get(content_url, headers=headers)
        assert original.status_code == 200
        assert original.headers["content-type"] == "image/png"
        assert original.content == source_bytes
        imported = await client.post(f"/api/v1/library-images/{image_id}/import", headers=headers)
        assert imported.status_code == 200
        asset_id = imported.json()["id"]
        assert imported.json()["width"] == 7
        assert imported.json()["height"] == 5
        assert app.state.job_service.db.fetchone("SELECT id FROM uploads WHERE id=?", (asset_id,)) is not None
        assert (source / "sample.png").read_bytes() == source_bytes


@pytest.mark.asyncio
async def test_library_thumbnail_is_small_cached_and_invalidated(tmp_path, monkeypatch):
    from app.api import public

    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    pairing = PairingService(tmp_path / "pairing.db")
    token = pairing.redeem_pairing_code(pairing.create_pairing_code(), "phone")
    source = tmp_path / "gallery"
    source.mkdir()
    image_path = source / "sample.png"
    image_path.write_bytes(_image_bytes("PNG", (2400, 1600)))
    libraries = SimpleNamespace(load=lambda: [SimpleNamespace(id="gallery", name="Gallery", path=str(source), enabled=True, recursive=True)])
    app = create_public_app(settings, pairing_service=pairing, library_service=libraries)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/libraries/gallery/images", headers=headers)
        image = listing.json()["images"][0]
        assert (await client.get(image["thumbnail_url"])).status_code == 401
        first = await client.get(image["thumbnail_url"], headers=headers)
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/webp"
        with Image.open(BytesIO(first.content)) as preview:
            assert preview.size == (384, 256)
        assert (await client.get(image["content_url"], headers=headers)).content == image_path.read_bytes()

        def unexpected_decode(*args, **kwargs):
            raise AssertionError("cached thumbnail should not decode the source again")

        original_open = public.Image.open
        monkeypatch.setattr(public.Image, "open", unexpected_decode)
        second = await client.get(image["thumbnail_url"], headers=headers)
        assert second.content == first.content
        monkeypatch.setattr(public.Image, "open", original_open)

        Image.new("RGB", (1200, 800), (250, 2, 2)).save(image_path)
        refreshed = await client.get(image["thumbnail_url"], headers=headers)
        assert refreshed.status_code == 200
        assert refreshed.content != first.content
        libraries.load = lambda: []
        assert (await client.get(image["thumbnail_url"], headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_library_thumbnail_keeps_orientation_and_transparency(tmp_path):
    settings = __import__("app.settings", fromlist=["Settings"]).Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    pairing = PairingService(tmp_path / "pairing.db")
    token = pairing.redeem_pairing_code(pairing.create_pairing_code(), "phone")
    source = tmp_path / "gallery"
    source.mkdir()
    (source / "oriented.jpg").write_bytes(_image_bytes("JPEG", (400, 200), orientation=6))
    transparent = Image.new("RGBA", (100, 50), (255, 0, 0, 0))
    transparent.save(source / "transparent.png")
    (source / "broken.png").write_bytes(b"not a png")
    libraries = SimpleNamespace(load=lambda: [SimpleNamespace(id="gallery", name="Gallery", path=str(source), enabled=True, recursive=True)])
    app = create_public_app(settings, pairing_service=pairing, library_service=libraries)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/libraries/gallery/images", headers=headers)
        urls = {row["name"]: row["thumbnail_url"] for row in listing.json()["images"]}
        oriented = await client.get(urls["oriented.jpg"], headers=headers)
        with Image.open(BytesIO(oriented.content)) as preview:
            assert preview.size == (192, 384)
        alpha = await client.get(urls["transparent.png"], headers=headers)
        with Image.open(BytesIO(alpha.content)) as preview:
            assert preview.convert("RGBA").getpixel((0, 0))[3] == 0
        assert (await client.get(urls["broken.png"], headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_image_upload_returns_dimensions_after_exif_transpose_for_supported_formats(tmp_path):
    app, headers = _paired_app(tmp_path)
    images = [
        ("tiny.png", "image/png", _image_bytes("PNG", (3, 2)), (3, 2)),
        ("portrait.jpg", "image/jpeg", _image_bytes("JPEG", (4, 2), orientation=6), (2, 4)),
        ("tiny.webp", "image/webp", _image_bytes("WEBP", (5, 4)), (5, 4)),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for filename, mime_type, content, expected in images:
            response = await client.post(
                "/api/v1/uploads/images",
                headers=headers,
                files={"files": (filename, content, mime_type)},
            )
            assert response.status_code == 200
            asset = response.json()["assets"][0]
            assert (asset["width"], asset["height"]) == expected


@pytest.mark.asyncio
async def test_malformed_image_bytes_are_rejected_after_existing_upload_checks(tmp_path):
    app, headers = _paired_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/uploads/images",
            headers=headers,
            files={"files": ("broken.png", b"not an image", "image/png")},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_image_upload_accepts_ten_references_but_rejects_eleven(tmp_path):
    app, headers = _paired_app(tmp_path)
    content = _image_bytes("PNG", (2, 2))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ten = await client.post(
            "/api/v1/uploads/images",
            headers=headers,
            files=[("files", (f"image-{index}.png", content, "image/png")) for index in range(10)],
        )
        eleven = await client.post(
            "/api/v1/uploads/images",
            headers=headers,
            files=[("files", (f"image-{index}.png", content, "image/png")) for index in range(11)],
        )
    assert ten.status_code == 200
    assert len(ten.json()["assets"]) == 10
    assert eleven.status_code == 422


@pytest.mark.asyncio
async def test_image_workflows_enforce_reference_rules_and_store_normalized_dimensions(tmp_path):
    app, headers = _paired_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        uploaded = await client.post(
            "/api/v1/uploads/images",
            headers=headers,
            files={"files": ("source.png", _image_bytes("PNG", (640, 480)), "image/png")},
        )
        asset_id = uploaded.json()["assets"][0]["id"]

        legacy = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={"prompt": "edit", "referenceAssetIds": [asset_id]},
        )
        assert legacy.status_code == 202
        legacy_payload = app.state.job_service.get_job(legacy.json()["id"])["payload"]
        assert legacy_payload["workflow"] == "qwen_edit_2511"

        legacy_extra = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={"prompt": "edit", "referenceAssetIds": [asset_id], "width": 640, "height": 480},
        )
        assert legacy_extra.status_code == 422

        scaled = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={
                "prompt": "edit",
                "workflow": "qwen_image_2_1_8gb_edit",
                "referenceAssetIds": [asset_id],
                "editSizeMode": "scale",
                "scaleFactor": 1.1,
            },
        )
        assert scaled.status_code == 202
        assert scaled.json()["workflow"] == "qwen_image_2_1_8gb_edit"
        scaled_payload = app.state.job_service.get_job(scaled.json()["id"])["payload"]
        assert (scaled_payload["width"], scaled_payload["height"]) == (704, 544)

        dimensions = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={
                "prompt": "edit",
                "workflow": "qwen_image_2_1_8gb_edit",
                "referenceAssetIds": [asset_id],
                "editSizeMode": "dimensions",
                "width": 641,
                "height": 479,
            },
        )
        assert dimensions.status_code == 202
        dimensions_payload = app.state.job_service.get_job(dimensions.json()["id"])["payload"]
        assert (dimensions_payload["width"], dimensions_payload["height"]) == (640, 480)

        mismatched_ratio = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={
                "prompt": "edit",
                "workflow": "qwen_image_2_1_8gb_edit",
                "referenceAssetIds": [asset_id],
                "editSizeMode": "dimensions",
                "width": 640,
                "height": 640,
            },
        )
        assert mismatched_ratio.status_code == 422

        t2i = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={
                "prompt": "sunrise",
                "workflow": "qwen_image_2_1_8gb_t2i",
                "referenceAssetIds": [],
                "width": 1024,
                "height": 768,
            },
        )
        assert t2i.status_code == 202
        assert t2i.json()["workflow"] == "qwen_image_2_1_8gb_t2i"
        t2i_payload = app.state.job_service.get_job(t2i.json()["id"])["payload"]
        assert (t2i_payload["width"], t2i_payload["height"]) == (1024, 768)

        t2i_with_reference = await client.post(
            "/api/v1/jobs/image",
            headers=headers,
            json={
                "prompt": "sunrise",
                "workflow": "qwen_image_2_1_8gb_t2i",
                "referenceAssetIds": [asset_id],
                "width": 1024,
                "height": 768,
            },
        )
        assert t2i_with_reference.status_code == 422


@pytest.mark.asyncio
async def test_image_workflows_reject_missing_unknown_and_oversized_parameters(tmp_path):
    app, headers = _paired_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        uploaded = await client.post(
            "/api/v1/uploads/images",
            headers=headers,
            files={"files": ("source.png", _image_bytes("PNG", (640, 480)), "image/png")},
        )
        asset_id = uploaded.json()["assets"][0]["id"]
        cases = [
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_edit", "referenceAssetIds": [asset_id]},
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_edit", "referenceAssetIds": [asset_id], "editSizeMode": "scale"},
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_edit", "referenceAssetIds": [asset_id], "editSizeMode": "scale", "scaleFactor": 1, "width": 640, "height": 480},
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_edit", "referenceAssetIds": [asset_id], "editSizeMode": "dimensions", "width": 2049, "height": 1536},
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_t2i", "referenceAssetIds": [], "width": 1025, "height": 768},
            {"prompt": "x", "workflow": "qwen_image_2_1_8gb_t2i", "referenceAssetIds": [], "width": 2048, "height": 2056},
            {"prompt": "x", "workflow": "unknown", "referenceAssetIds": [asset_id]},
        ]
        for payload in cases:
            response = await client.post("/api/v1/jobs/image", headers=headers, json=payload)
            assert response.status_code == 422, payload


@pytest.mark.parametrize("orientation", [5, 6, 7, 8])
def test_image_dimensions_reads_exif_orientation_without_transposing_pixels(monkeypatch, orientation):
    def unexpected_transpose(*args, **kwargs):
        raise AssertionError("metadata parsing must not transpose image pixels")

    monkeypatch.setattr(ImageOps, "exif_transpose", unexpected_transpose)
    assert _image_dimensions(_image_bytes("JPEG", (4, 2), orientation=orientation)) == (2, 4)


def test_image_dimensions_converts_decompression_bombs_to_a_safe_validation_error(monkeypatch):
    def bomb(_content):
        raise Image.DecompressionBombError("image too large")

    monkeypatch.setattr("app.api.public.Image.open", bomb)
    with pytest.raises(ValueError, match="image dimensions exceed safety limit"):
        _image_dimensions(b"header")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scale_factor", "1.0"),
        ("scale_factor", True),
        ("width", "640"),
        ("width", 640.0),
        ("width", True),
        ("height", "480"),
        ("height", 480.0),
        ("height", True),
    ],
)
def test_image_request_rejects_coerced_numeric_strings_and_booleans(field, value):
    payload = {
        "prompt": "edit",
        "workflow": "qwen_image_2_1_8gb_edit",
        "referenceAssetIds": ["asset_1"],
        "editSizeMode": "scale" if field == "scale_factor" else "dimensions",
    }
    if field == "scale_factor":
        payload["scaleFactor"] = value
    else:
        payload.update({"width": 640, "height": 480})
        payload["width" if field == "width" else "height"] = value
    with pytest.raises(ValidationError):
        ImageJobRequest.model_validate(payload)


@pytest.mark.parametrize("value", [1, 1.25])
def test_image_request_accepts_json_numbers_for_scale_factor(value):
    request = ImageJobRequest.model_validate(
        {
            "prompt": "edit",
            "workflow": "qwen_image_2_1_8gb_edit",
            "referenceAssetIds": ["asset_1"],
            "editSizeMode": "scale",
            "scaleFactor": value,
        }
    )
    assert request.scale_factor == value
