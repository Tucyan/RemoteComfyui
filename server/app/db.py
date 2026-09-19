from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable


class Database:
    """SQLite boundary with per-operation connections for safe async use."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with self._lock, self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS pairings (id TEXT PRIMARY KEY, code_hash TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL, used_at REAL);
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL, last_seen_at REAL, revoked_at REAL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('image', 'video')), status TEXT NOT NULL, payload_json TEXT NOT NULL, prompt_id TEXT, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS job_inputs (job_id TEXT NOT NULL, position INTEGER NOT NULL, asset_id TEXT, filename TEXT NOT NULL, PRIMARY KEY(job_id, position), FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, filename TEXT NOT NULL, storage_path TEXT NOT NULL, mime_type TEXT NOT NULL, size INTEGER NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, mime_type TEXT NOT NULL, storage_path TEXT NOT NULL, size INTEGER NOT NULL, created_at REAL NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);
                CREATE TABLE IF NOT EXISTS library_images (id TEXT PRIMARY KEY, library_id TEXT NOT NULL, relative_path TEXT NOT NULL, storage_path TEXT NOT NULL, mime_type TEXT NOT NULL, size INTEGER NOT NULL, mtime REAL NOT NULL, UNIQUE(library_id, relative_path));
                CREATE TABLE IF NOT EXISTS library_roots (id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, recursive INTEGER NOT NULL, enabled INTEGER NOT NULL);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "started_at" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN started_at REAL")

    @staticmethod
    def json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def json_loads(value: str) -> Any:
        return json.loads(value)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> int:
        with self._lock, self.connect() as connection:
            return connection.execute(sql, tuple(parameters)).rowcount

    def fetchone(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock, self.connect() as connection:
            return connection.execute(sql, tuple(parameters)).fetchone()

    def fetchall(self, sql: str, parameters: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock, self.connect() as connection:
            return list(connection.execute(sql, tuple(parameters)).fetchall())

    def transaction(self):
        return _Transaction(self)


class _Transaction:
    def __init__(self, database: Database):
        self.database = database
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self.database._lock.acquire()
        self.connection = self.database.connect()
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, exc_type, exc, traceback) -> None:
        assert self.connection is not None
        try:
            (self.connection.rollback if exc_type else self.connection.commit)()
        finally:
            self.connection.close()
            self.database._lock.release()
