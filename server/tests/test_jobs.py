from __future__ import annotations

import asyncio

import pytest

from app.comfy.client import ComfyUIClient
from app.db import Database
from app.jobs.service import JobService


class FakeComfy:
    def __init__(self):
        self.queued = []
        self.uploaded = []
        self.history_calls = 0

    async def upload_image(self, filename, content, **kwargs):
        self.uploaded.append(filename)
        return {"name": filename, "subfolder": "", "type": "input"}

    async def queue_prompt(self, prompt, **kwargs):
        self.queued.append(prompt)
        return {"prompt_id": "prompt-123"}

    async def get_history(self, prompt_id):
        self.history_calls += 1
        return {
            prompt_id: {
                "status": {"completed": True},
                "outputs": {"22": {"images": [{"filename": "result.png", "subfolder": "", "type": "output"}]}},
            }
        }


@pytest.mark.asyncio
async def test_job_service_serializes_execution_and_persists_prompt_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    comfy = FakeComfy()
    service = JobService(db, comfy, tmp_path)
    first = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    second = service.create_job("image", {"reference_images": ["two.png"], "prompt": "two"})

    await service.run_once()
    await service.run_once()
    assert [job["status"] for job in service.list_jobs()] == ["succeeded", "succeeded"]
    assert service.get_job(first["id"])["prompt_id"] == "prompt-123"
    assert service.get_job(second["id"])["prompt_id"] == "prompt-123"
    assert comfy.history_calls == 2


def test_restart_reconciliation_uses_persisted_prompt_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    service = JobService(db, FakeComfy(), tmp_path)
    row = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    service.mark_submitted(row["id"], "prompt-after-restart")

    asyncio.run(service.reconcile())
    assert service.get_job(row["id"])["status"] == "succeeded"


def test_artifact_ids_hide_storage_paths_and_support_ranges(tmp_path):
    db = Database(tmp_path / "jobs.db")
    service = JobService(db, FakeComfy(), tmp_path)
    row = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    artifact = service.add_artifact(row["id"], "image/png", b"0123456789", "private\\nested\\result.png")
    assert artifact["id"]
    assert "private" not in artifact
    assert "path" not in artifact
    assert service.read_artifact(artifact["id"], 2, 5) == (b"2345", 10, "image/png")
