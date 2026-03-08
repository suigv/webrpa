from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from engine.models.manifest import PluginManifest
from engine.parser import parse_manifest

logger = logging.getLogger(__name__)

_shared_loader_lock = threading.Lock()
_shared_loaders: dict[Path, "PluginLoader"] = {}


class PluginEntry:
    """A loaded and validated plugin ready for execution."""

    def __init__(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        self.manifest = manifest
        self.plugin_dir = plugin_dir

    @property
    def script_path(self) -> Path:
        return self.plugin_dir / self.manifest.entry_script


class PluginLoader:
    """Scans plugins/ directory for YAML plugin manifests."""

    def __init__(self, plugins_root: Optional[Path] = None) -> None:
        if plugins_root is None:
            plugins_root = Path(__file__).resolve().parents[1] / "plugins"
        self._root = plugins_root
        self._plugins: Dict[str, PluginEntry] = {}

    def scan(self) -> None:
        """Scan plugins directory and load all valid manifests."""
        self._plugins.clear()
        if not self._root.is_dir():
            logger.warning("plugins directory not found: %s", self._root)
            return

        for child in sorted(self._root.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                manifest = parse_manifest(manifest_path)
                entry = PluginEntry(manifest=manifest, plugin_dir=child)
                if not entry.script_path.exists():
                    logger.warning(
                        "plugin %s: entry_script %s not found",
                        manifest.name,
                        entry.script_path,
                    )
                    continue
                self._plugins[manifest.name] = entry
                logger.info("loaded plugin: %s (v%s)", manifest.name, manifest.version)
            except Exception as exc:
                logger.warning("failed to load plugin from %s: %s", child, exc)

    def get(self, name: str) -> Optional[PluginEntry]:
        return self._plugins.get(name)

    def has(self, name: str) -> bool:
        return name in self._plugins

    @property
    def names(self) -> list[str]:
        return sorted(self._plugins.keys())


def _default_plugins_root() -> Path:
    return Path(__file__).resolve().parents[1] / "plugins"


def _resolved_plugins_root(plugins_root: Optional[Path] = None) -> Path:
    return (plugins_root or _default_plugins_root()).resolve()


def clear_shared_plugin_loader_cache() -> None:
    with _shared_loader_lock:
        _shared_loaders.clear()


def get_shared_plugin_loader(plugins_root: Optional[Path] = None, *, refresh: bool = False) -> PluginLoader:
    root = _resolved_plugins_root(plugins_root)
    with _shared_loader_lock:
        loader = _shared_loaders.get(root)
        if loader is None:
            loader = PluginLoader(plugins_root=root)
            loader.scan()
            _shared_loaders[root] = loader
        elif refresh:
            loader.scan()
        return loader


def build_scanned_plugin_loader(plugins_root: Optional[Path] = None, *, refresh: bool = False) -> PluginLoader:
    shared = get_shared_plugin_loader(plugins_root=plugins_root, refresh=refresh)
    loader = PluginLoader(plugins_root=shared._root)
    loader._plugins = dict(shared._plugins)
    return loader
