from __future__ import annotations

import json

import httpx
import pytest

from app.comfy.client import ComfyUIClient, ComfyUIError


@pytest.mark.asyncio
async def test_client_uploads_prompt_and_reads_history_queue_and_view():
    seen: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/upload/image":
            body = await request.aread()
            assert b'filename="reference.png"' in body
            assert b"image-bytes" in body
            return httpx.Response(200, json={"name": "reference.png", "subfolder": "", "type": "input"})
        if request.url.path == "/prompt":
            payload = json.loads((await request.aread()).decode())
            assert payload["prompt"] == {"1": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}}}
            assert payload["client_id"] == "client-1"
            return httpx.Response(200, json={"prompt_id": "prompt-1", "number": 1, "node_errors": {}})
        if request.url.path == "/history/prompt-1":
            return httpx.Response(200, json={"prompt-1": {"status": {"completed": True}}})
        if request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        if request.url.path == "/view":
            assert request.url.params["filename"] == "result.png"
            assert request.url.params["type"] == "output"
            return httpx.Response(200, content=b"result-bytes", headers={"content-type": "image/png"})
        return httpx.Response(404)

    client = ComfyUIClient(transport=httpx.MockTransport(handler))
    uploaded = await client.upload_image("reference.png", b"image-bytes")
    queued = await client.queue_prompt({"1": {"class_type": "LoadImage", "inputs": {"image": "reference.png"}}}, client_id="client-1")
    history = await client.get_history("prompt-1")
    queue = await client.get_queue()
    viewed = await client.view("result.png")

    assert uploaded["name"] == "reference.png"
    assert queued["prompt_id"] == "prompt-1"
    assert history["prompt-1"]["status"]["completed"] is True
    assert queue["queue_pending"] == []
    assert viewed == b"result-bytes"
    assert ("POST", "/upload/image") in seen
    assert ("POST", "/prompt") in seen


def test_client_rejects_non_loopback_comfyui_url():
    with pytest.raises(ValueError, match="loopback"):
        ComfyUIClient("http://192.168.1.20:8188")


@pytest.mark.asyncio
async def test_client_translates_http_and_transport_failures_without_raw_details():
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="C:\\private\\model.safetensors")

    client = ComfyUIClient(transport=httpx.MockTransport(failing_handler))
    with pytest.raises(ComfyUIError, match="request failed") as error:
        await client.get_queue()
    assert "private" not in str(error.value)

    async def network_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret host", request=request)

    client = ComfyUIClient(transport=httpx.MockTransport(network_handler))
    with pytest.raises(ComfyUIError, match="unavailable"):
        await client.get_queue()
