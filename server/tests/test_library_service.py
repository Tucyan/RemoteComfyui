import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from app.libraries.models import LibraryRoot
from app.libraries.service import LibraryService, PathValidationError, WindowsFilesystem


class FakeFS:
    def __init__(self):
        self._dirs = {
            "C:\\": ["C:\\Pictures", "C:\\System Volume Information"],
            "C:\\Pictures": ["C:\\Pictures\\Sub", "C:\\Pictures\\.hidden"],
        }

    def drives(self):
        return ["C:\\", "\\\\server\\share", "D:\\"]

    def directories(self, path):
        return self._dirs.get(path, [])

    def canonical(self, path):
        return path.rstrip("\\") + "\\" if len(path) == 2 else path

    def validate_directory(self, path):
        canonical = self.canonical(path)
        if canonical not in {"C:\\", "C:\\Pictures", "C:\\Pictures\\Sub"}:
            raise PathValidationError("directory does not exist or is not readable")
        return canonical


def test_directory_listing_filters_files_hidden_and_unc_drives(tmp_path):
    service = LibraryService(tmp_path, filesystem=FakeFS())
    assert service.list_drives() == ["C:\\", "D:\\"]
    assert service.list_directories("C:\\") == ["C:\\Pictures"]
    assert service.list_directories("C:\\Pictures") == ["C:\\Pictures\\Sub"]


def test_rejects_path_attacks_and_duplicate_or_nested_roots(tmp_path):
    service = LibraryService(tmp_path, filesystem=FakeFS())
    with pytest.raises(PathValidationError):
        service.validate_path("C:\\Pictures\\..\\Pictures")
    with pytest.raises(PathValidationError):
        service.validate_path("\\\\server\\share")
    service.create(LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures"))
    with pytest.raises(PathValidationError):
        service.create(LibraryRoot(id="sub", name="Sub", path="C:\\Pictures\\Sub"))
    with pytest.raises(PathValidationError):
        service.create(LibraryRoot(id="dup", name="Duplicate", path="C:\\Pictures"))


@pytest.mark.parametrize("path", [r"\\?\C:\Pictures", r"\\.\C:\Pictures"])
def test_rejects_windows_device_paths(tmp_path, path):
    service = LibraryService(tmp_path, filesystem=FakeFS())
    with pytest.raises(PathValidationError):
        service.validate_path(path)


def test_load_returns_empty_when_data_dir_and_config_are_missing(tmp_path):
    data_dir = tmp_path / "missing-data"
    service = LibraryService(data_dir, filesystem=FakeFS())

    assert service.load() == []
    assert not data_dir.exists()


def test_atomic_update_keeps_backups_and_never_deletes_source(tmp_path):
    source = tmp_path / "original.png"
    source.write_bytes(b"keep")
    service = LibraryService(tmp_path, filesystem=FakeFS())
    service.create(LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures"))
    service.update("pictures", enabled=False)
    assert source.read_bytes() == b"keep"
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "config.yaml.bak.1").exists()


def test_load_rejects_external_yaml_with_invalid_root(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "libraries:\n  - id: pictures\n    name: Pictures\n    path: relative\\pictures\n",
        encoding="utf-8",
    )
    service = LibraryService(tmp_path, filesystem=FakeFS())
    with pytest.raises(ValueError, match="invalid library configuration"):
        service.load()


def test_save_validates_paths_and_collection_without_mutating_inputs(tmp_path):
    service = LibraryService(tmp_path, filesystem=FakeFS())
    invalid = LibraryRoot(id="pictures", name="Pictures", path="relative\\pictures")
    with pytest.raises(PathValidationError):
        service.save([invalid])
    assert invalid.path == "relative\\pictures"
    assert not (tmp_path / "config.yaml").exists()

    parent = LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures")
    child = LibraryRoot(id="sub", name="Sub", path="C:\\Pictures\\Sub")
    service.save([parent])
    original_config = (tmp_path / "config.yaml").read_bytes()
    with pytest.raises(PathValidationError):
        service.save([parent, child])
    assert (tmp_path / "config.yaml").read_bytes() == original_config


def test_load_canonicalizes_and_validates_library_models(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "libraries:\n  - id: Pictures\n    name: Pictures\n    path: C:\\\\Pictures\n",
        encoding="utf-8",
    )
    service = LibraryService(tmp_path, filesystem=FakeFS())
    with pytest.raises(ValueError, match="invalid library configuration"):
        service.load()


def test_save_retains_only_five_config_backups(tmp_path):
    service = LibraryService(tmp_path, filesystem=FakeFS())
    for index in range(7):
        service.save([LibraryRoot(id="pictures", name=f"Pictures {index}", path="C:\\Pictures")])
    assert [path.name for path in tmp_path.glob("config.yaml.bak.*")] == [
        "config.yaml.bak.1",
        "config.yaml.bak.2",
        "config.yaml.bak.3",
        "config.yaml.bak.4",
        "config.yaml.bak.5",
    ]
    assert not (tmp_path / "config.yaml.bak.6").exists()


def test_concurrent_creates_keep_both_roots_and_valid_yaml(tmp_path):
    class OverlappingFS(FakeFS):
        def __init__(self):
            super().__init__()
            self._dirs["C:\\Pictures2"] = []
            self._valid_paths = {"C:\\Pictures", "C:\\Pictures2"}
            self._calls = 0
            self._calls_lock = threading.Lock()
            self.first_validating = threading.Event()
            self.second_loaded = threading.Event()

        def validate_directory(self, path):
            with self._calls_lock:
                self._calls += 1
                call = self._calls
            if call == 1:
                self.first_validating.set()
                # Without transaction locking, the second create has loaded
                # the same stale document before the first write proceeds.
                self.second_loaded.wait(timeout=2)
            elif call == 2:
                self.second_loaded.set()
                while not (tmp_path / "config.yaml").exists():
                    if not self.first_validating.wait(timeout=0.01):
                        break
            if path in self._valid_paths:
                return path
            return super().validate_directory(path)

    filesystem = OverlappingFS()
    first = LibraryService(tmp_path, filesystem=filesystem)
    second = LibraryService(tmp_path, filesystem=filesystem)

    def create(service, library):
        return service.create(library)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(create, first, LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures"))
        assert filesystem.first_validating.wait(timeout=2)
        second_future = executor.submit(create, second, LibraryRoot(id="pictures2", name="Pictures 2", path="C:\\Pictures2"))
        assert first_future.result(timeout=5).id == "pictures"
        assert second_future.result(timeout=5).id == "pictures2"

    payload = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert {row["id"] for row in payload["libraries"]} == {"pictures", "pictures2"}
    for backup in sorted(tmp_path.glob("config.yaml.bak.*")):
        backup_payload = yaml.safe_load(backup.read_text(encoding="utf-8"))
        assert isinstance(backup_payload, dict)
        assert isinstance(backup_payload.get("libraries"), list)


def test_windows_directory_provider_filters_files_hidden_system_denied_and_caps(monkeypatch):
    class Entry:
        def __init__(self, name, is_dir=True):
            self.name = name
            self.path = f"C:\\{name}"
            self._is_dir = is_dir

        def is_dir(self, follow_symlinks=False):
            return self._is_dir

    entries = [
        Entry("photo.png", is_dir=False),
        Entry(".hidden"),
        Entry("system"),
        Entry("denied"),
        Entry("allowed"),
    ] + [Entry(f"folder-{index:03d}") for index in range(600)]

    class Scanner:
        def __enter__(self):
            return entries

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(os, "scandir", lambda path: Scanner())
    monkeypatch.setattr(os, "access", lambda path, mode: not path.endswith("denied"))
    monkeypatch.setattr(WindowsFilesystem, "_hidden_or_system", staticmethod(lambda path: path.endswith("system")))

    directories = WindowsFilesystem().directories("C:\\")
    assert len(directories) == 500
    assert "C:\\allowed" in directories
    assert all(not path.endswith(("photo.png", ".hidden", "system", "denied")) for path in directories)
