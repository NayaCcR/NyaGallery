from __future__ import annotations

from nyagallery.plugin_runtime import PluginRegistry, RegisteredPlugin
from nyagallery.plugins import PluginManifest


DEFAULT_PLUGIN_MANIFESTS = (
    PluginManifest("core.media", "1.0.0", ("transcode",), permissions=("read_assets",)),
    PluginManifest("core.storage", "1.0.0", ("storage",), permissions=("read_assets", "write_assets")),
    PluginManifest("core.notifications", "1.0.0", ("notification",), permissions=("notify",)),
)


def install_default_plugins(registry: PluginRegistry) -> None:
    """Register no-op built-ins; core behavior remains available if plugins are disabled."""
    for manifest in DEFAULT_PLUGIN_MANIFESTS:
        if any(item["name"] == manifest.name for item in registry.snapshot()):
            continue
        registry.register(RegisteredPlugin(manifest=manifest, start=lambda: None, stop=lambda: None))


def default_plugin_status(registry: PluginRegistry) -> dict[str, object]:
    return {"available": True, "plugins": registry.snapshot(), "core_fallback": True}
