from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class LibraryRoot:
    id: str
    name: str
    path: str
    recursive: bool = True
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
