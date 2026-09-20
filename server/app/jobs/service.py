from __future__ import annotations

import mimetypes
import asyncio
import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

from ..comfy.workflows import build_minimax_prompt, build_qwen_prompt
from ..db import Database
from .models import JOB_STATES


class JobService:
    def __init__(self, database: Database | str, comfy: Any, data_dir: str | Path, *, clock=time.time):
        self.db = database if isinstance(database, Database) else Database(database)
        self.comfy = comfy
        self.data_dir = Path(data_dir)
        self.clock = clock
        self.artifact_dir = self.data_dir / "artifacts"
        self._worker_task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None

    def create_job(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind not in {"image", "video"}:
            raise ValueError("unsupported job kind")
        now = self.clock()
        job_id = "job_" + secrets.token_urlsafe(12)
        self.db.execute("INSERT INTO jobs(id,kind,status,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", (job_id, kind, "queued", self.db.json_dumps(payload), now, now))
        for position, item in enumerate(payload.get("reference_files", [])):
            self.db.execute("INSERT INTO job_inputs(job_id,position,asset_id,filename) VALUES(?,?,?,?)", (job_id, position, item.get("asset_id"), item.get("filename", "reference")))
        return self.get_job(job_id)

    def wake_worker(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def start_worker(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._wake = asyncio.Event()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop_worker(self) -> None:
        task, self._worker_task = self._worker_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(self) -> None:
        assert self._wake is not None
        await self.reconcile()
        while True:
            processed = await self.run_once()
            if processed is not None:
                continue
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                await self.reconcile()
            self._wake.clear()

    def get_job(self, job_id: str) -> dict[str, Any]:
        row = self.db.fetchone("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row is None:
            raise KeyError(job_id)
        result = dict(row)
        result["payload"] = self.db.json_loads(result.pop("payload_json"))
        result["artifacts"] = self.list_artifacts(job_id)
        return result

    def list_jobs(self, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        if status is not None and status not in JOB_STATES:
            raise ValueError("invalid job status")
        rows = self.db.fetchall("SELECT id FROM jobs WHERE (? IS NULL OR status=?) ORDER BY created_at DESC LIMIT ?", (status, status, limit))
        return [self.get_job(row["id"]) for row in rows]

    def mark_submitted(self, job_id: str, prompt_id: str) -> None:
        self.db.execute("UPDATE jobs SET status='submitted',prompt_id=?,updated_at=? WHERE id=?", (prompt_id, self.clock(), job_id))

    def mark_running(self, job_id: str) -> None:
        now = self.clock()
        self.db.execute("UPDATE jobs SET status='running',started_at=COALESCE(started_at,?),updated_at=? WHERE id=?", (now, now, job_id))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.db.transaction() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] == "queued":
                connection.execute("UPDATE jobs SET status='canceled',updated_at=? WHERE id=?", (self.clock(), job_id))
        return self.get_job(job_id)

    async def run_once(self) -> dict[str, Any] | None:
        with self.db.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            connection.execute("UPDATE jobs SET status='uploading',updated_at=? WHERE id=?", (self.clock(), row["id"]))
        job_id = row["id"]
        payload = self.db.json_loads(row["payload_json"])
        try:
            references = list(payload.get("reference_images", []))
            for index, upload in enumerate(payload.get("reference_files", [])):
                result = await self.comfy.upload_image(upload["filename"], Path(upload["path"]).read_bytes(), content_type=upload.get("mime_type", "application/octet-stream"))
                if isinstance(result, dict) and isinstance(result.get("name"), str) and result["name"]:
                    references[index] = result["name"]
            if row["kind"] == "image":
                prompt = build_qwen_prompt(references, payload["prompt"], seed=payload.get("seed"))
            else:
                prompt = build_minimax_prompt(references, payload["prompt"], width=payload.get("width", 1344), height=payload.get("height", 768), frames=payload.get("frames", 124), seed=payload.get("seed"))
            queued = await self.comfy.queue_prompt(prompt, client_id="remote-comfyui")
            prompt_id = queued.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id:
                raise RuntimeError("ComfyUI did not return a prompt id")
            self.mark_submitted(job_id, prompt_id)
            history = await self.comfy.get_history(prompt_id)
            await self._apply_history(job_id, prompt_id, history)
        except Exception as exc:
            self.db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (str(exc)[:500], self.clock(), job_id))
        return self.get_job(job_id)

    async def reconcile(self) -> None:
        rows = self.db.fetchall("SELECT id,prompt_id FROM jobs WHERE status IN ('submitted','running') AND prompt_id IS NOT NULL")
        for row in rows:
            try:
                await self._apply_history(row["id"], row["prompt_id"], await self.comfy.get_history(row["prompt_id"]))
            except Exception:
                continue

    async def _apply_history(self, job_id: str, prompt_id: str, history: dict[str, Any]) -> None:
        record = history.get(prompt_id) if isinstance(history, dict) else None
        if not isinstance(record, dict):
            self.mark_running(job_id)
            return
        status = record.get("status", {})
        if status.get("status_str") == "error":
            message = "ComfyUI execution failed"
            for event in reversed(status.get("messages", [])):
                if isinstance(event, (list, tuple)) and len(event) == 2 and event[0] == "execution_error" and isinstance(event[1], dict):
                    detail = event[1].get("exception_message")
                    if isinstance(detail, str) and detail.strip():
                        message = f"ComfyUI execution failed: {detail.strip()}"
                    break
            self.db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (message[:500], self.clock(), job_id))
            return
        if not status.get("completed") and status.get("status_str") not in {"success", "succeeded"}:
            self.mark_running(job_id)
            return
        for output in _iter_outputs(record.get("outputs", {})):
            try:
                content = await self.comfy.view(output["filename"], subfolder=output.get("subfolder", ""), folder_type=output.get("type", "output"))
            except Exception:
                continue
            mime = mimetypes.guess_type(output["filename"])[0] or "application/octet-stream"
            self.add_artifact(job_id, mime, content, output["filename"])
        self.db.execute("UPDATE jobs SET status='succeeded',updated_at=? WHERE id=?", (self.clock(), job_id))

    def add_artifact(self, job_id: str, mime_type: str, content: bytes, source_name: str) -> dict[str, Any]:
        digest = hashlib.sha256(content).digest()
        for row in self.db.fetchall(
            "SELECT * FROM artifacts WHERE job_id=? AND mime_type=? AND size=?",
            (job_id, mime_type, len(content)),
        ):
            existing_path = Path(row["storage_path"])
            try:
                if existing_path.is_file() and hashlib.sha256(existing_path.read_bytes()).digest() == digest:
                    return self._artifact_response(row)
            except OSError:
                continue
        artifact_id = "artifact_" + secrets.token_urlsafe(12)
        suffix = Path(source_name).suffix.lower()[:10] or ".bin"
        path = self.artifact_dir / f"{artifact_id}{suffix}"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.db.execute("INSERT INTO artifacts(id,job_id,mime_type,storage_path,size,created_at) VALUES(?,?,?,?,?,?)", (artifact_id, job_id, mime_type, str(path), len(content), self.clock()))
        return self._artifact_response(self.db.fetchone("SELECT * FROM artifacts WHERE id=?", (artifact_id,)))

    def list_artifacts(self, job_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.db.fetchall("SELECT * FROM artifacts" + (" WHERE job_id=?" if job_id else "") + " ORDER BY created_at", (job_id,) if job_id else ())
        return [self._artifact_response(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        row = self.db.fetchone("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
        if row is None:
            raise KeyError(artifact_id)
        return self._artifact_response(row)

    def delete_artifact(self, artifact_id: str) -> None:
        row = self.db.fetchone("SELECT storage_path FROM artifacts WHERE id=?", (artifact_id,))
        if row is None:
            raise KeyError(artifact_id)
        path = Path(row["storage_path"]).resolve()
        if path.parent != self.artifact_dir.resolve():
            raise PermissionError("artifact path is outside storage")
        path.unlink(missing_ok=True)
        self.db.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))

    def read_artifact(self, artifact_id: str, start: int = 0, end: int | None = None) -> tuple[bytes, int, str]:
        row = self.db.fetchone("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
        if row is None:
            raise KeyError(artifact_id)
        path = Path(row["storage_path"]).resolve()
        if self.artifact_dir.resolve() not in path.parents:
            raise PermissionError("artifact path is outside storage")
        total = int(row["size"])
        start = max(0, min(start, total))
        end = total - 1 if end is None else max(start, min(end, total - 1))
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(max(0, end - start + 1))
        return data, total, row["mime_type"]

    @staticmethod
    def _artifact_response(row: Any) -> dict[str, Any]:
        return {"id": row["id"], "job_id": row["job_id"], "mime_type": row["mime_type"], "size": row["size"], "created_at": row["created_at"]}


def _iter_outputs(outputs: Any):
    if not isinstance(outputs, dict):
        return
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("images", "gifs", "videos"):
            values = node_output.get(key, [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict) and isinstance(value.get("filename"), str):
                        yield value
