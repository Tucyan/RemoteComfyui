from __future__ import annotations

import ctypes
import ntpath
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

import yaml

from .models import LibraryRoot


class PathValidationError(ValueError):
    pass


class LibraryConfigError(ValueError):
    """The persisted library document contains invalid model data."""


class FilesystemProviderError(RuntimeError):
    """The injected filesystem provider failed independently of path validity."""


class LibraryLockError(FilesystemProviderError):
    """The library configuration lock could not be acquired before its deadline."""


class FilesystemProvider(Protocol):
    def drives(self) -> list[str]: ...

    def directories(self, path: str) -> list[str]: ...

    def validate_directory(self, path: str) -> str: ...


class WindowsFilesystem:
    """Small injectable filesystem boundary used by the service and API."""

    def drives(self) -> list[str]:
        if os.name != "nt":
            return []
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        result: list[str] = []
        for index in range(26):
            if mask & (1 << index):
                drive = f"{chr(65 + index)}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                if drive_type == 3:  # DRIVE_FIXED
                    result.append(drive)
        return result

    def directories(self, path: str) -> list[str]:
        result: list[str] = []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name.startswith(".") or self._hidden_or_system(entry.path):
                        continue
                    try:
                        if not os.access(entry.path, os.R_OK):
                            continue
                    except OSError:
                        continue
                    result.append(entry.path)
        except (OSError, PermissionError):
            return []
        return sorted(result, key=str.casefold)[:500]

    @staticmethod
    def _hidden_or_system(path: str) -> bool:
        if os.name != "nt":
            return False
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            return attrs != -1 and bool(attrs & 0x6)  # HIDDEN | SYSTEM
        except Exception:
            return False

    def validate_directory(self, path: str) -> str:
        _check_windows_path_shape(path)
        if os.name != "nt":
            raise PathValidationError("Windows fixed-drive paths are required")
        if path[:2].upper() not in {drive[:2].upper() for drive in self.drives()}:
            raise PathValidationError("path must be on a fixed local drive")
        candidate = Path(path)
        try:
            resolved = candidate.resolve(strict=True)
            if not resolved.is_dir() or not os.access(resolved, os.R_OK):
                raise PathValidationError("directory does not exist or is not readable")
            _check_windows_path_shape(str(resolved))
            if str(resolved)[:2].upper() not in {drive[:2].upper() for drive in self.drives()}:
                raise PathValidationError("path must be on a fixed local drive")
        except (OSError, RuntimeError) as exc:
            raise PathValidationError("directory does not exist or is not readable") from exc
        return str(resolved)


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _check_windows_path_shape(path: str) -> None:
    if not isinstance(path, str) or not path.strip():
        raise PathValidationError("path must be a non-empty absolute directory")
    value = path.strip()
    if value.startswith(("\\\\", "//", "\\?.", "\\\\.\\")):
        raise PathValidationError("UNC and device paths are not allowed")
    if ".." in value.replace("/", "\\").split("\\"):
        raise PathValidationError("parent path segments are not allowed")
    if len(value) < 3 or not re.match(r"^[A-Za-z]:[\\/]", value):
        raise PathValidationError("path must be an absolute fixed-drive directory")


def _is_parent(parent: str, child: str) -> bool:
    parent_norm = parent.rstrip("\\/").casefold() + "\\"
    child_norm = child.rstrip("\\/").casefold() + "\\"
    return child_norm.startswith(parent_norm)


class LibraryService:
    _process_locks: dict[str, Any] = {}
    _process_locks_guard = threading.Lock()

    def __init__(
        self,
        data_dir: str | Path,
        filesystem: FilesystemProvider | None = None,
        *,
        lock_timeout: float = 10.0,
    ):
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.yaml"
        self.lock_path = self.data_dir / ".config.lock"
        self.filesystem = filesystem or WindowsFilesystem()
        self.lock_timeout = max(0.0, float(lock_timeout))

    def list_drives(self) -> list[str]:
        try:
            drives = self.filesystem.drives()
        except Exception as exc:
            raise FilesystemProviderError from exc
        return [
            drive for drive in drives
            if isinstance(drive, str)
            and len(drive) >= 3
            and drive[0].isalpha()
            and drive[1] == ":"
            and drive[2] in "\\/"
        ]

    def list_directories(self, path: str | None = None) -> list[str]:
        if path is None:
            return self.list_drives()
        canonical = self.validate_path(path)
        result = []
        try:
            children = self.filesystem.directories(canonical)
        except Exception as exc:
            raise FilesystemProviderError from exc
        for child in children:
            name = ntpath.basename(str(child).rstrip("\\/"))
            if name.startswith(".") or name.casefold() == "system volume information":
                continue
            result.append(str(child))
        return result[:500]

    def validate_path(self, path: str) -> str:
        _check_windows_path_shape(path)
        try:
            if not self._is_fixed_drive(path):
                raise PathValidationError("path must be on a fixed local drive")
            return self.filesystem.validate_directory(path)
        except PathValidationError:
            raise
        except FilesystemProviderError:
            raise
        except Exception as exc:
            raise FilesystemProviderError from exc

    def _is_fixed_drive(self, path: str) -> bool:
        if not isinstance(path, str) or len(path) < 2:
            return False
        prefix = path[:2].upper()
        try:
            drives = self.filesystem.drives()
        except Exception as exc:
            raise FilesystemProviderError from exc
        return any(str(drive)[:2].upper() == prefix and not str(drive).startswith(("\\\\", "//")) for drive in drives)

    def load(self) -> list[LibraryRoot]:
        if not self.data_dir.exists():
            return []
        with self._configuration_lock():
            return self._load_unlocked()

    def _load_unlocked(self) -> list[LibraryRoot]:
        if not self.config_path.exists():
            return []
        try:
            raw = self.config_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("invalid library configuration") from exc
        try:
            payload = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise ValueError("invalid library configuration") from exc
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get("libraries", []), list):
                raise ValueError("libraries must be a list")
            rows = payload.get("libraries", [])
            parsed = [self._from_dict(row) for row in rows]
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise ValueError("invalid library configuration") from exc
        try:
            return self._validate_libraries(parsed)
        except (PathValidationError, LibraryConfigError) as exc:
            raise ValueError("invalid library configuration") from exc

    def save(self, libraries: list[LibraryRoot]) -> None:
        with self._configuration_lock(create=True):
            validated = self._validate_libraries(libraries)
            self._save_unlocked(validated)

    def _save_unlocked(self, libraries: list[LibraryRoot]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {"libraries": [library.to_dict() for library in libraries]}
        encoded = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")
        if self.config_path.exists():
            for index in range(5, 1, -1):
                old = self.data_dir / f"config.yaml.bak.{index - 1}"
                new = self.data_dir / f"config.yaml.bak.{index}"
                if old.exists():
                    os.replace(old, new)
            shutil.copy2(self.config_path, self.data_dir / "config.yaml.bak.1")
        fd, temp_name = tempfile.mkstemp(prefix=".config.", suffix=".yaml", dir=self.data_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.config_path)
            try:
                directory_fd = os.open(self.data_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @classmethod
    def _process_lock_for(cls, path: Path) -> Any:
        key = os.path.normcase(str(path.resolve(strict=False)))
        with cls._process_locks_guard:
            lock = cls._process_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._process_locks[key] = lock
            return lock

    @contextmanager
    def _configuration_lock(self, *, create: bool = False) -> Iterator[None]:
        if create:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        elif not self.data_dir.exists():
            yield
            return

        process_lock = self._process_lock_for(self.lock_path)
        if not process_lock.acquire(timeout=self.lock_timeout):
            raise LibraryLockError("library configuration lock unavailable")
        handle = None
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.lock_path.open("a+b")
            self._acquire_file_lock(handle)
        except Exception:
            if handle is not None:
                handle.close()
            process_lock.release()
            raise
        try:
            yield
        finally:
            try:
                self._release_file_lock(handle)
            finally:
                handle.close()
                process_lock.release()

    def _acquire_file_lock(self, handle: Any) -> None:
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    raise LibraryLockError("library configuration lock unavailable") from exc
                time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))

    @staticmethod
    def _release_file_lock(handle: Any) -> None:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    @staticmethod
    def _from_dict(row: Any) -> LibraryRoot:
        if not isinstance(row, dict):
            raise ValueError("library must be an object")
        if not isinstance(row.get("id"), str) or not isinstance(row.get("name"), str) or not isinstance(row.get("path"), str):
            raise ValueError("library id, name, and path must be strings")
        return LibraryRoot(
            id=row["id"], name=row["name"], path=row["path"],
            recursive=bool(row.get("recursive", True)), enabled=bool(row.get("enabled", True)),
        )

    @staticmethod
    def _validate_model(library: LibraryRoot) -> None:
        if not isinstance(library, LibraryRoot):
            raise LibraryConfigError("library must be an object")
        if not isinstance(library.id, str) or not isinstance(library.name, str):
            raise LibraryConfigError("library id and name must be strings")
        if not _SLUG.fullmatch(library.id):
            raise LibraryConfigError("id must be a lowercase slug")
        if not library.name or not library.name.strip():
            raise LibraryConfigError("name must not be empty")

    def _validated_copy(self, library: LibraryRoot) -> LibraryRoot:
        self._validate_model(library)
        if not isinstance(library.path, str):
            raise LibraryConfigError("path must be a string")
        return LibraryRoot(
            id=library.id,
            name=library.name,
            path=self.validate_path(library.path),
            recursive=bool(library.recursive),
            enabled=bool(library.enabled),
        )

    def _validate_libraries(self, libraries: list[LibraryRoot]) -> list[LibraryRoot]:
        if not isinstance(libraries, list):
            raise ValueError("libraries must be a list")
        validated: list[LibraryRoot] = []
        for library in libraries:
            candidate = self._validated_copy(library)
            if any(
                candidate.id == existing.id
                or candidate.path.casefold() == existing.path.casefold()
                or _is_parent(candidate.path, existing.path)
                or _is_parent(existing.path, candidate.path)
                for existing in validated
            ):
                if any(candidate.id == existing.id for existing in validated):
                    raise LibraryConfigError("library id already exists")
                raise PathValidationError("library paths must not duplicate or nest")
            validated.append(candidate)
        return validated

    def _validate_collection(self, libraries: list[LibraryRoot], candidate: LibraryRoot, exclude_id: str | None = None) -> LibraryRoot:
        validated_candidate = self._validated_copy(candidate)
        for existing in libraries:
            if existing.id == exclude_id:
                continue
            existing_path = self.validate_path(existing.path)
            if validated_candidate.path.casefold() == existing_path.casefold() or _is_parent(validated_candidate.path, existing_path) or _is_parent(existing_path, validated_candidate.path):
                raise PathValidationError("library paths must not duplicate or nest")
        return validated_candidate

    def create(self, library: LibraryRoot) -> LibraryRoot:
        with self._configuration_lock(create=True):
            libraries = self._load_unlocked()
            if any(item.id == library.id for item in libraries):
                raise ValueError("library id already exists")
            library = self._validate_collection(libraries, library)
            libraries.append(library)
            self._save_unlocked(libraries)
            return library

    def update(self, library_id: str, **changes: Any) -> LibraryRoot:
        with self._configuration_lock(create=True):
            libraries = self._load_unlocked()
            current = next((item for item in libraries if item.id == library_id), None)
            if current is None:
                raise KeyError(library_id)
            candidate = LibraryRoot(**{**current.to_dict(), **changes})
            candidate = self._validate_collection(libraries, candidate, exclude_id=library_id)
            libraries[libraries.index(current)] = candidate
            self._save_unlocked(libraries)
            return candidate

    def delete(self, library_id: str) -> None:
        with self._configuration_lock(create=True):
            libraries = self._load_unlocked()
            remaining = [item for item in libraries if item.id != library_id]
            if len(remaining) == len(libraries):
                raise KeyError(library_id)
            self._save_unlocked(remaining)
