from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    plugin_types: tuple[str, ...]
    permissions: tuple[str, ...] = ()
    core_min_version: str | None = None
    dependencies: tuple[str, ...] = ()

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
