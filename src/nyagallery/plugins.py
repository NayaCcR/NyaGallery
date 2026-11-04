from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from zipfile import ZipFile


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    plugin_types: tuple[str, ...]
    permissions: tuple[str, ...] = ()
    core_min_version: str | None = None
    dependencies: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PluginManifest":
        if not isinstance(payload, dict):
            raise ValueError("plugin manifest must be an object")
        def strings(key: str) -> tuple[str, ...]:
            value = payload.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"plugin manifest field {key} must be a string list")
            return tuple(item.strip() for item in value if item.strip())
        name = payload.get("name")
        version = payload.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError("plugin manifest name and version must be strings")
        core_min_version = payload.get("core_min_version")
        if core_min_version is not None and not isinstance(core_min_version, str):
            raise ValueError("core_min_version must be a string")
        return cls(name=name.strip(), version=version.strip(), plugin_types=strings("plugin_types"), permissions=strings("permissions"), core_min_version=core_min_version, dependencies=strings("dependencies"))

    @classmethod
    def from_json(cls, path: str | Path) -> "PluginManifest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_package(cls, path: str | Path) -> "PluginManifest":
        with ZipFile(path) as package:
            try:
                content = package.read("plugin.json")
            except KeyError as exc:
                raise ValueError("plugin package must contain plugin.json") from exc
        return cls.from_dict(json.loads(content.decode("utf-8")))

    def validate(self, *, core_version: str, granted_permissions: set[str]) -> None:
        if not self.name or not self.version:
            raise ValueError("plugin name and version are required")
        if not self.plugin_types or any(not item.strip() for item in self.plugin_types):
            raise ValueError("plugin_types must not be empty")
        missing = set(self.permissions) - granted_permissions
        if missing:
            raise PermissionError(f"plugin permissions not granted: {sorted(missing)}")
        if self.core_min_version and _version_tuple(core_version) < _version_tuple(self.core_min_version):
            raise RuntimeError(f"plugin requires core >= {self.core_min_version}")

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "version": self.version, "plugin_types": list(self.plugin_types), "permissions": list(self.permissions), "core_min_version": self.core_min_version, "dependencies": list(self.dependencies)}


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split(".")[:3])
    except ValueError as exc:
        raise ValueError(f"invalid version: {value}") from exc
