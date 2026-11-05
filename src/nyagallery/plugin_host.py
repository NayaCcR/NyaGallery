"""Plugin host: the bridge between the FastAPI app and the plugin registry.

Plugins are Python objects that implement :class:`Plugin`. Official plugins ship inside the
``nyagallery_plugins`` package; third-party plugins are folders under ``<storage>/plugins/<name>/``
containing ``plugin.json`` plus an entry module. Each plugin receives a :class:`PluginContext`
scoped to its declared permissions.

Routes are registered once at startup (FastAPI cannot remove routes at runtime). Every route a
plugin registers carries a guard dependency that answers 404 while the plugin is disabled, so
enabling / disabling takes effect immediately without a restart.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from nyagallery.plugin_runtime import PluginRegistry, RegisteredPlugin
from nyagallery.plugins import PluginManifest

LOGGER = logging.getLogger("nyagallery.plugins")

# Permissions a plugin may request. Official plugins are granted all of them; third-party
# plugins get exactly what their manifest lists (validated against this set).
KNOWN_PERMISSIONS = frozenset(
    {
        "routes",  # register HTTP routes
        "events",  # subscribe to core events
        "read_assets",
        "write_assets",
        "network",  # talk to external services
        "credentials",  # read / write stored platform credentials
        "notify",
        "read_config",
    }
)

# Core events plugins can subscribe to. Payloads are plain dicts.
CORE_EVENTS = frozenset({"asset.created", "sync.finished", "transcode.finished", "plugin.enabled", "plugin.disabled"})


class Plugin(Protocol):
    """What a plugin module exposes as ``plugin`` (or returns from ``create_plugin()``)."""

    manifest: PluginManifest

    def setup(self, ctx: "PluginContext") -> None:
        """Called once at startup, enabled or not. Register routes / event handlers here."""

    def start(self) -> None:
        """Called when the plugin becomes enabled."""

    def stop(self) -> None:
        """Called when the plugin is disabled or the app shuts down."""


@dataclass
class PluginInfo:
    """Static metadata shown in the admin UI, beyond the manifest."""

    title: str = ""
    description: str = ""
    official: bool = False
    # Admin sections / features the frontend should hide while the plugin is disabled.
    provides_sections: tuple[str, ...] = ()
    default_enabled: bool = True


class PluginContext:
    """Capability object handed to a plugin; every method checks the plugin's permissions."""

    def __init__(self, host: "PluginHost", manifest: PluginManifest, info: PluginInfo) -> None:
        self._host = host
        self.manifest = manifest
        self.info = info
        self.name = manifest.name

    def _require(self, permission: str) -> None:
        if permission not in self.manifest.permissions:
            raise PermissionError(f"plugin {self.name} lacks permission {permission!r}")

    @property
    def app_state(self) -> Any:
        """The core AppState (storage, sessions, config). Official plugins only."""
        if not self.info.official:
            raise PermissionError("app state is only available to official plugins")
        return self._host.app.state.nyagallery

    def router(self, *, prefix: str = "", tags: list[str] | None = None) -> APIRouter:
        """An APIRouter whose routes 404 while this plugin is disabled.

        Official plugins may use any prefix (to keep existing URLs); third-party plugins are
        confined to ``/api/plugins/<name>``.
        """
        self._require("routes")
        if not self.info.official:
            prefix = f"/api/plugins/{self.name}{prefix}"
        router = APIRouter(prefix=prefix, tags=tags or [f"plugin:{self.name}"], dependencies=[Depends(self._host.guard(self.name))])
        self._host._routers.append((self.name, router))
        return router

    def on(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._require("events")
        if event not in CORE_EVENTS:
            raise ValueError(f"unknown event {event!r}")
        self._host._handlers.setdefault(event, []).append((self.name, handler))

    def config(self) -> dict[str, Any]:
        self._require("read_config")
        return dict(self._host.plugin_config(self.name))


@dataclass
class _Loaded:
    plugin: Any
    info: PluginInfo
    source: str  # "official" | path of a third-party folder
    error: str | None = None
    context: PluginContext | None = field(default=None, repr=False)


class PluginHost:
    def __init__(self, app: FastAPI, *, core_version: str, state_path: Path | None, plugins_dir: Path | None) -> None:
        self.app = app
        self.core_version = core_version
        self.plugins_dir = plugins_dir
        self.registry = PluginRegistry(core_version=core_version, permissions=set(KNOWN_PERMISSIONS), state_path=state_path)
        self._loaded: dict[str, _Loaded] = {}
        self._failed: dict[str, dict[str, Any]] = {}
        self._routers: list[tuple[str, APIRouter]] = []
        self._handlers: dict[str, list[tuple[str, Callable[[dict[str, Any]], None]]]] = {}
        self._lock = threading.RLock()

    # ---- loading -------------------------------------------------------------------------
    def load_official(self, modules: list[str]) -> None:
        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
                self._add(self._plugin_from_module(module), source="official", official=True)
            except Exception as exc:  # a broken official plugin must not take the core down
                LOGGER.exception("official plugin %s failed to load", module_name)
                self._failed[module_name] = {"name": module_name, "source": "official", "error": f"{type(exc).__name__}: {exc}"}

    def load_third_party(self) -> None:
        if self.plugins_dir is None or not self.plugins_dir.is_dir():
            return
        for folder in sorted(path for path in self.plugins_dir.iterdir() if path.is_dir()):
            manifest_path = folder / "plugin.json"
            if not manifest_path.is_file():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(raw)
                unknown = set(manifest.permissions) - KNOWN_PERMISSIONS
                if unknown:
                    raise PermissionError(f"unknown permissions: {sorted(unknown)}")
                if manifest.name.startswith("official."):
                    raise ValueError("the official. namespace is reserved")
                entry = str(raw.get("entry") or "plugin.py")
                entry_path = (folder / entry).resolve()
                if folder.resolve() not in entry_path.parents:
                    raise ValueError("plugin entry must stay inside the plugin folder")
                spec = importlib.util.spec_from_file_location(f"nyagallery_thirdparty_{manifest.name.replace('.', '_')}", entry_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"cannot load {entry_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                plugin = self._plugin_from_module(module)
                if plugin.manifest != manifest:
                    plugin.manifest = manifest  # plugin.json is authoritative for third-party plugins
                info = getattr(module, "PLUGIN_INFO", None) or PluginInfo(title=str(raw.get("title") or manifest.name), description=str(raw.get("description") or ""))
                info.official = False
                info.default_enabled = False  # third-party plugins start disabled until an admin enables them
                self._add(plugin, source=str(folder), official=False, info=info)
            except Exception as exc:
                LOGGER.warning("third-party plugin %s failed to load: %s", folder.name, exc)
                self._failed[folder.name] = {"name": folder.name, "source": str(folder), "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _plugin_from_module(module: Any) -> Any:
        plugin = getattr(module, "plugin", None)
        if plugin is None and callable(getattr(module, "create_plugin", None)):
            plugin = module.create_plugin()
        if plugin is None or not isinstance(getattr(plugin, "manifest", None), PluginManifest):
            raise ValueError("plugin module must expose `plugin` (or create_plugin()) with a PluginManifest")
        for method in ("setup", "start", "stop"):
            if not callable(getattr(plugin, method, None)):
                raise ValueError(f"plugin must implement {method}()")
        return plugin

    def _add(self, plugin: Any, *, source: str, official: bool, info: PluginInfo | None = None) -> None:
        info = info or getattr(plugin, "info", None) or PluginInfo(title=plugin.manifest.name)
        info.official = official
        name = plugin.manifest.name
        if name in self._loaded:
            raise ValueError(f"duplicate plugin {name}")
        self.registry.register(RegisteredPlugin(manifest=plugin.manifest, start=plugin.start, stop=plugin.stop))
        loaded = _Loaded(plugin=plugin, info=info, source=source)
        loaded.context = PluginContext(self, plugin.manifest, info)
        self._loaded[name] = loaded
        try:
            plugin.setup(loaded.context)
        except Exception as exc:
            loaded.error = f"setup failed: {type(exc).__name__}: {exc}"
            LOGGER.exception("plugin %s setup failed", name)

    def mount_routes(self) -> None:
        for _name, router in self._routers:
            self.app.include_router(router)

    def restore(self) -> None:
        """Enable plugins: saved state wins; otherwise the plugin's default_enabled."""
        saved: dict[str, bool] = {}
        if self.registry.state_path and self.registry.state_path.is_file():
            try:
                for item in json.loads(self.registry.state_path.read_text(encoding="utf-8")):
                    if isinstance(item, dict) and "name" in item:
                        saved[str(item["name"])] = bool(item.get("enabled"))
            except (OSError, ValueError):
                LOGGER.warning("plugin state file is unreadable; using defaults")
        # dependencies first: simple topological order over enabled candidates
        pending = [name for name, loaded in self._loaded.items() if loaded.error is None and saved.get(name, loaded.info.default_enabled)]
        for _ in range(len(pending) + 1):
            progressed = False
            for name in list(pending):
                deps = self._loaded[name].plugin.manifest.dependencies
                if all(self.is_enabled(dep) for dep in deps):
                    try:
                        self.registry.enable(name)
                    except Exception as exc:
                        self._loaded[name].error = f"start failed: {type(exc).__name__}: {exc}"
                    pending.remove(name)
                    progressed = True
            if not progressed:
                break
        for name in pending:
            self._loaded[name].error = "dependencies not enabled: " + ", ".join(self._loaded[name].plugin.manifest.dependencies)
        self.registry.persist()

    # ---- runtime -------------------------------------------------------------------------
    def is_enabled(self, name: str) -> bool:
        return any(item["name"] == name and item["enabled"] for item in self.registry.snapshot())

    def guard(self, name: str) -> Callable[[], None]:
        def _guard() -> None:
            if not self.is_enabled(name):
                raise HTTPException(status_code=404, detail=f"plugin {name} is disabled")

        _guard.__name__ = f"plugin_guard_{name.replace('.', '_')}"
        return _guard

    def enable(self, name: str) -> None:
        with self._lock:
            loaded = self._require_loaded(name)
            if loaded.error and loaded.error.startswith("setup failed"):
                raise RuntimeError(loaded.error)
            self.registry.enable(name)
            loaded.error = None
        self.emit("plugin.enabled", {"name": name})

    def disable(self, name: str) -> None:
        with self._lock:
            self._require_loaded(name)
            self.registry.disable(name)
        self.emit("plugin.disabled", {"name": name})

    def _require_loaded(self, name: str) -> _Loaded:
        loaded = self._loaded.get(name)
        if loaded is None:
            raise KeyError(name)
        return loaded

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        """Deliver an event to enabled subscribers; a failing handler never breaks the caller."""
        for plugin_name, handler in list(self._handlers.get(event, [])):
            if not self.is_enabled(plugin_name):
                continue
            try:
                handler(payload)
            except Exception:
                LOGGER.warning("plugin %s handler for %s failed:\n%s", plugin_name, event, traceback.format_exc())

    def plugin_config(self, name: str) -> dict[str, Any]:
        config = getattr(self.app.state.nyagallery, "config", None)
        plugins = getattr(config, "plugins", None) if config is not None else None
        if isinstance(plugins, dict):
            value = plugins.get(name)
            return value if isinstance(value, dict) else {}
        return {}

    def stop_all(self) -> None:
        for item in reversed(self.registry.snapshot()):
            if item["enabled"]:
                try:
                    self._loaded[item["name"]].plugin.stop()
                except Exception:
                    LOGGER.warning("plugin %s stop failed during shutdown", item["name"])

    def disabled_sections(self) -> list[str]:
        sections: list[str] = []
        for name, loaded in self._loaded.items():
            if not self.is_enabled(name):
                sections.extend(loaded.info.provides_sections)
        return sorted(set(sections))

    def snapshot(self) -> list[dict[str, Any]]:
        enabled = {item["name"]: item["enabled"] for item in self.registry.snapshot()}
        dependents: dict[str, list[str]] = {}
        for name, loaded in self._loaded.items():
            for dep in loaded.plugin.manifest.dependencies:
                dependents.setdefault(dep, []).append(name)
        items = []
        for name, loaded in self._loaded.items():
            items.append(
                {
                    **loaded.plugin.manifest.to_dict(),
                    "title": loaded.info.title or name,
                    "description": loaded.info.description,
                    "official": loaded.info.official,
                    "source": "official" if loaded.info.official else loaded.source,
                    "enabled": bool(enabled.get(name)),
                    "error": loaded.error,
                    "provides_sections": list(loaded.info.provides_sections),
                    "dependents": sorted(dependents.get(name, [])),
                    "routes": sum(len(router.routes) for owner, router in self._routers if owner == name),
                    "events": sorted(event for event, handlers in self._handlers.items() if any(owner == name for owner, _ in handlers)),
                }
            )
        for failed in self._failed.values():
            items.append({"name": failed["name"], "version": "", "plugin_types": [], "permissions": [], "dependencies": [], "core_min_version": None, "title": failed["name"], "description": "", "official": failed["source"] == "official", "source": failed["source"], "enabled": False, "error": failed["error"], "provides_sections": [], "dependents": [], "routes": 0, "events": []})
        return sorted(items, key=lambda item: (not item["official"], item["name"]))
