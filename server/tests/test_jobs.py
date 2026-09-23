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


@pytest.mark.asyncio
async def test_history_reprocessing_does_not_duplicate_same_artifact(tmp_path):
    class VideoComfy(FakeComfy):
        async def view(self, filename, **kwargs):
            return b"video-bytes"

    service = JobService(Database(tmp_path / "jobs.db"), VideoComfy(), tmp_path)
    job = service.create_job("video", {"reference_images": ["one.png"], "prompt": "one"})
    history = {
        "prompt-1": {
            "status": {"completed": True},
            "outputs": {"24": {"images": [{"filename": "result.mp4", "subfolder": "", "type": "output"}]}},
        }
    }

    await service._apply_history(job["id"], "prompt-1", history)
    await service._apply_history(job["id"], "prompt-1", history)

    artifacts = service.list_artifacts(job["id"])
    assert len(artifacts) == 1


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


@pytest.mark.asyncio
async def test_worker_defaults_missing_image_workflow_to_legacy_qwen_2511(tmp_path):
    comfy = FakeComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    service.create_job("image", {"reference_images": ["legacy.png"], "prompt": "legacy edit", "seed": 7})

    await service.run_once()

    prompt = comfy.queued[0]
    assert prompt["11"]["inputs"]["unet_name"] == "qwen_image_edit_2511_int8_convrot.safetensors"
    assert prompt["15"]["inputs"]["prompt"] == "legacy edit"
    assert prompt["20"]["inputs"]["seed"] == 7


@pytest.mark.asyncio
async def test_worker_dispatches_video_with_ordered_uploads_and_settings(tmp_path):
    comfy = RenamingComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    first = tmp_path / "video-first.png"
    second = tmp_path / "video-second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    service.create_job(
        "video",
        {
            "reference_images": ["video-first.png", "video-second.png"],
            "reference_files": [
                {"asset_id": "first", "filename": "video-first.png", "path": str(first)},
                {"asset_id": "second", "filename": "video-second.png", "path": str(second)},
            ],
            "prompt": "camera push in",
            "width": 640,
            "height": 480,
            "frames": 124,
            "seed": 123,
        },
    )

    await service.run_once()

    prompt = comfy.queued[0]
    video = prompt["19"]["inputs"]
    assert comfy.uploaded == ["video-first.png", "video-second.png"]
    assert [prompt[str(index)]["inputs"]["image"] for index in (1, 2)] == ["renamed-1.png", "renamed-2.png"]
    assert video["prompt"] == "camera push in"
    assert video["width"] == 640
    assert video["height"] == 480
    assert video["length"] == 124
    assert video["ref_images.ref_image_0"] == ["1", 0]
    assert video["ref_images.ref_image_1"] == ["2", 0]
    assert prompt["16"]["inputs"]["noise_seed"] == 123


@pytest.mark.asyncio
async def test_worker_dispatches_qwen_21_edit_with_ordered_uploads_and_dimensions(tmp_path):
    comfy = RenamingComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    service.create_job(
        "image",
        {
            "workflow": "qwen_image_2_1_8gb_edit",
            "reference_images": ["first.png", "second.png"],
            "reference_files": [
                {"asset_id": "first", "filename": "first.png", "path": str(first)},
                {"asset_id": "second", "filename": "second.png", "path": str(second)},
            ],
            "prompt": "replace the sky",
            "width": 1024,
            "height": 768,
            "seed": 42,
        },
    )

    await service.run_once()

    prompt = comfy.queued[0]
    assert comfy.uploaded == ["first.png", "second.png"]
    assert [prompt[str(index)]["inputs"]["image"] for index in (1, 2)] == ["renamed-1.png", "renamed-2.png"]
    assert prompt["474"]["inputs"]["prompt"] == "replace the sky"
    assert prompt["456"]["inputs"]["width"] == 1024
    assert prompt["456"]["inputs"]["height"] == 768
    assert prompt["458"]["inputs"]["seed"] == 42


@pytest.mark.asyncio
async def test_worker_dispatches_qwen_21_t2i_without_uploading_or_passing_references(tmp_path):
    comfy = RenamingComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    reference = tmp_path / "should-not-upload.png"
    reference.write_bytes(b"reference")

    service.create_job(
        "image",
        {
            "workflow": "qwen_image_2_1_8gb_t2i",
            "reference_images": ["should-not-upload.png"],
            "reference_files": [{"asset_id": "ignored", "filename": "should-not-upload.png", "path": str(reference)}],
            "prompt": "a red fox",
            "width": 1024,
            "height": 768,
            "seed": 99,
        },
    )

    await service.run_once()

    prompt = comfy.queued[0]
    assert comfy.uploaded == []
    assert "1" not in prompt
    assert not any(node.get("class_type") == "LoadImage" for node in prompt.values())
    assert not any(
        key.startswith("images.")
        for node in prompt.values()
        for key in node.get("inputs", {})
    )
    assert prompt["452"]["inputs"]["prompt"] == "a red fox"
    assert prompt["456"]["inputs"]["width"] == 1024
    assert prompt["456"]["inputs"]["height"] == 768
    assert prompt["458"]["inputs"]["seed"] == 99


@pytest.mark.asyncio
async def test_worker_fails_unknown_image_workflow_without_queueing(tmp_path):
    comfy = FakeComfy()
    service = JobService(Database(tmp_path / "jobs.db"), comfy, tmp_path)
    job = service.create_job(
        "image",
        {"workflow": "unknown", "reference_images": ["reference.png"], "prompt": "should fail"},
    )

    result = await service.run_once()

    assert result["status"] == "failed"
    assert "unsupported image workflow" in result["error"]
    assert comfy.queued == []
