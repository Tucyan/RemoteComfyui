from pathlib import Path

import pytest

from app.libraries.models import LibraryRoot
from app.libraries.service import LibraryService, PathValidationError


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


def test_atomic_update_keeps_backups_and_never_deletes_source(tmp_path):
    source = tmp_path / "original.png"
    source.write_bytes(b"keep")
    service = LibraryService(tmp_path, filesystem=FakeFS())
    service.create(LibraryRoot(id="pictures", name="Pictures", path="C:\\Pictures"))
    service.update("pictures", enabled=False)
    assert source.read_bytes() == b"keep"
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "config.yaml.bak.1").exists()

