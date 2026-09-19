from __future__ import annotations

import ctypes
import ntpath
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

import yaml

from .models import LibraryRoot


class PathValidationError(ValueError):
    pass


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
    def __init__(self, data_dir: str | Path, filesystem: FilesystemProvider | None = None):
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.yaml"
        self.filesystem = filesystem or WindowsFilesystem()

    def list_drives(self) -> list[str]:
        return [drive for drive in self.filesystem.drives() if self._is_fixed_drive(drive)]

    def list_directories(self, path: str | None = None) -> list[str]:
        if path is None:
            return self.list_drives()
        canonical = self.validate_path(path)
        result = []
        for child in self.filesystem.directories(canonical):
            name = ntpath.basename(str(child).rstrip("\\/"))
            if name.startswith(".") or name.casefold() == "system volume information":
                continue
            result.append(str(child))
        return result[:500]

    def validate_path(self, path: str) -> str:
        _check_windows_path_shape(path)
        if not self._is_fixed_drive(path):
            raise PathValidationError("path must be on a fixed local drive")
        return self.filesystem.validate_directory(path)

    def _is_fixed_drive(self, path: str) -> bool:
        if not isinstance(path, str) or len(path) < 2:
            return False
        prefix = path[:2].upper()
        return any(str(drive)[:2].upper() == prefix and not str(drive).startswith(("\\\\", "//")) for drive in self.filesystem.drives())

    def load(self) -> list[LibraryRoot]:
        if not self.config_path.exists():
            return []
        try:
            payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            rows = payload.get("libraries", []) if isinstance(payload, dict) else []
            return [self._from_dict(row) for row in rows]
        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            raise ValueError("invalid library configuration") from exc

    def save(self, libraries: list[LibraryRoot]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for library in libraries:
            self._validate_model(library)
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

    @staticmethod
    def _from_dict(row: Any) -> LibraryRoot:
        if not isinstance(row, dict):
            raise ValueError("library must be an object")
        return LibraryRoot(
            id=str(row["id"]), name=str(row["name"]), path=str(row["path"]),
            recursive=bool(row.get("recursive", True)), enabled=bool(row.get("enabled", True)),
        )

    @staticmethod
    def _validate_model(library: LibraryRoot) -> None:
        if not _SLUG.fullmatch(library.id):
            raise ValueError("id must be a lowercase slug")
        if not library.name or not library.name.strip():
            raise ValueError("name must not be empty")

    def _validate_collection(self, libraries: list[LibraryRoot], candidate: LibraryRoot, exclude_id: str | None = None) -> LibraryRoot:
        self._validate_model(candidate)
        canonical = self.validate_path(candidate.path)
        for existing in libraries:
            if existing.id == exclude_id:
                continue
            existing_path = self.validate_path(existing.path)
            if canonical.casefold() == existing_path.casefold() or _is_parent(canonical, existing_path) or _is_parent(existing_path, canonical):
                raise PathValidationError("library paths must not duplicate or nest")
        candidate.path = canonical
        return candidate

    def create(self, library: LibraryRoot) -> LibraryRoot:
        libraries = self.load()
        if any(item.id == library.id for item in libraries):
            raise ValueError("library id already exists")
        self._validate_collection(libraries, library)
        libraries.append(library)
        self.save(libraries)
        return library

    def update(self, library_id: str, **changes: Any) -> LibraryRoot:
        libraries = self.load()
        current = next((item for item in libraries if item.id == library_id), None)
        if current is None:
            raise KeyError(library_id)
        candidate = LibraryRoot(**{**current.to_dict(), **changes})
        self._validate_collection(libraries, candidate, exclude_id=library_id)
        libraries[libraries.index(current)] = candidate
        self.save(libraries)
        return candidate

    def delete(self, library_id: str) -> None:
        libraries = self.load()
        remaining = [item for item in libraries if item.id != library_id]
        if len(remaining) == len(libraries):
            raise KeyError(library_id)
        self.save(remaining)
