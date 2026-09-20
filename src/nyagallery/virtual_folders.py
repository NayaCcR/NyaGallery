"""Virtual folders are named, persisted tag queries; physical files never move."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VirtualFolder:
    name: str
    query: str
    group: str = "custom"
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "query": self.query, "group": self.group, "description": self.description}


class VirtualFolderCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._folders: dict[str, VirtualFolder] = {}

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for item in data.get("folders", []) if isinstance(data, dict) else ():
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                folder = VirtualFolder(
                    name=str(item["name"]),
                    query=str(item.get("query") or ""),
                    group=str(item.get("group") or "custom"),
                    description=str(item.get("description") or ""),
                )
                self._folders[folder.name] = folder

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": "nyagallery.virtual_folders.v1", "folders": [item.to_dict() for item in self.list()]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def put(self, folder: VirtualFolder) -> None:
        if not folder.name.strip() or not folder.query.strip():
            raise ValueError("virtual folder name and query are required")
        self._folders[folder.name] = folder

    def remove(self, name: str) -> bool:
        return self._folders.pop(name, None) is not None

    def get(self, name: str) -> VirtualFolder | None:
        return self._folders.get(name)

    def list(self) -> list[VirtualFolder]:
        return sorted(self._folders.values(), key=lambda item: (item.group, item.name.casefold()))
