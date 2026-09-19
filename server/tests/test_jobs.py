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


class RenamingComfy(FakeComfy):
    async def upload_image(self, filename, content, **kwargs):
        self.uploaded.append(filename)
        return {"name": f"renamed-{len(self.uploaded)}.png", "subfolder": "", "type": "input"}


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


@pytest.mark.asyncio
async def test_reconciliation_marks_comfyui_execution_error_as_failed(tmp_path):
    class ErroredComfy(FakeComfy):
        async def get_history(self, prompt_id):
            return {prompt_id: {"status": {"completed": False, "status_str": "error", "messages": [
                ["execution_error", {"node_type": "MiniMaxH3ReferenceToVideo", "exception_message": "unexpected keyword argument 'ref_image_1'"}],
            ]}}}

    service = JobService(Database(tmp_path / "jobs.db"), ErroredComfy(), tmp_path)
    row = service.create_job("video", {"reference_images": ["one.png"], "prompt": "one"})
    service.mark_submitted(row["id"], "prompt-error")
    await service.reconcile()

    result = service.get_job(row["id"])
    assert result["status"] == "failed"
    assert "unexpected keyword argument 'ref_image_1'" in result["error"]


def test_artifact_ids_hide_storage_paths_and_support_ranges(tmp_path):
    db = Database(tmp_path / "jobs.db")
    service = JobService(db, FakeComfy(), tmp_path)
    row = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    artifact = service.add_artifact(row["id"], "image/png", b"0123456789", "private\\nested\\result.png")
    assert artifact["id"]
    assert "private" not in artifact
    assert "path" not in artifact
    assert service.read_artifact(artifact["id"], 2, 5) == (b"2345", 10, "image/png")


def test_delete_artifact_removes_local_file_and_database_row(tmp_path):
    service = JobService(Database(tmp_path / "jobs.db"), FakeComfy(), tmp_path)
    job = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    artifact = service.add_artifact(job["id"], "image/png", b"pixels", "result.png")
    stored = service.db.fetchone("SELECT storage_path FROM artifacts WHERE id=?", (artifact["id"],))
    path = __import__("pathlib").Path(stored["storage_path"])

    service.delete_artifact(artifact["id"])

    assert not path.exists()
    assert service.db.fetchone("SELECT id FROM artifacts WHERE id=?", (artifact["id"],)) is None
    with pytest.raises(KeyError):
        service.delete_artifact(artifact["id"])


def test_delete_artifact_refuses_path_outside_artifact_directory(tmp_path):
    service = JobService(Database(tmp_path / "jobs.db"), FakeComfy(), tmp_path)
    job = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    artifact = service.add_artifact(job["id"], "image/png", b"pixels", "result.png")
    outside = tmp_path / "keep.png"
    outside.write_bytes(b"keep")
    service.db.execute("UPDATE artifacts SET storage_path=? WHERE id=?", (str(outside), artifact["id"]))

    with pytest.raises(PermissionError):
        service.delete_artifact(artifact["id"])
    assert outside.read_bytes() == b"keep"


def test_running_start_time_stays_stable_during_reconciliation(tmp_path):
    current = [100.0]
    service = JobService(Database(tmp_path / "jobs.db"), FakeComfy(), tmp_path, clock=lambda: current[0])
    job = service.create_job("image", {"reference_images": ["one.png"], "prompt": "one"})
    service.mark_submitted(job["id"], "prompt-1")
    current[0] = 120.0
    service.mark_running(job["id"])
    current[0] = 150.0
    service.mark_running(job["id"])
    assert service.get_job(job["id"])["started_at"] == 120.0


@pytest.mark.asyncio
async def test_worker_uses_comfyui_renamed_reference_filenames(tmp_path):
    comfy = RenamingComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    service.create_job("image", {"reference_images": ["same.png", "same.png"], "reference_files": [{"asset_id": "a", "filename": "same.png", "path": str(first)}, {"asset_id": "b", "filename": "same.png", "path": str(second)}], "prompt": "edit"})
    await service.run_once()
    assert comfy.queued
    names = [inputs["image"] for node in comfy.queued[0].values() for inputs in [node.get("inputs", {})] if isinstance(inputs.get("image"), str)]
    assert "renamed-1.png" in names
    assert "renamed-2.png" in names
