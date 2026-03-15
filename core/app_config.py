from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.paths import project_root

logger = logging.getLogger(__name__)

_cached_package_map: Dict[str, str] = {}
_last_scan_time: float = 0
_SCAN_TTL = 60.0

class AppConfigManager:
    """管理应用配置 (*.yaml) 的发现、枚举和自动骨架生成。"""
    
    @staticmethod
    def get_apps_dir() -> Path:
        """返回应用配置文件的搜索目录。"""
        return project_root() / "config" / "apps"

    @classmethod
    def get_package_to_app_map(cls, refresh: bool = False) -> Dict[str, str]:
        """获取 Android 包名到 App 配置文件名的映射。"""
        global _cached_package_map, _last_scan_time
        now = time.time()
        if refresh or not _cached_package_map or (now - _last_scan_time) > _SCAN_TTL:
            cls._scan_apps()
            _last_scan_time = now
        return _cached_package_map

    @classmethod
    def _scan_apps(cls):
        global _cached_package_map
        mapping: Dict[str, str] = {}
        
        search_dirs = [project_root() / "config" / "apps"]
        seen_apps = set()
        
        for apps_dir in search_dirs:
            if not apps_dir.exists():
                continue
            for yaml_path in apps_dir.glob("*.yaml"):
                app_name = yaml_path.stem
                if app_name in seen_apps:
                    continue
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        doc = yaml.safe_load(f)
                        if isinstance(doc, dict) and "package_name" in doc:
                            pkg = str(doc["package_name"]).strip()
                            if pkg:
                                mapping[pkg] = app_name
                    seen_apps.add(app_name)
                except Exception:
                    continue
        _cached_package_map = mapping

    @classmethod
    def find_app_by_package(cls, package: str) -> Optional[str]:
        """根据包名查找对应的 App 配置名。"""
        if not package:
            return None
        return cls.get_package_to_app_map().get(package.strip())

    @classmethod
    def load_app_config(cls, app_name: str) -> Dict[str, Any]:
        """加载指定的 App 配置文件内容。"""
        repo_root = project_root()
        search_paths = [
            repo_root / "config" / "apps" / f"{app_name}.yaml"
        ]
        
        for path in search_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    logger.error("Failed to load app config %s: %s", path, e)
        
        return {}

    @classmethod
    def bootstrap_app_config(cls, app_package: str, app_name: Optional[str] = None):
        """为未知包名创建基础配置文件骨架。"""
        if not app_package:
            return
            
        app_id = app_name or app_package.split('.')[-1]
        target_dir = project_root() / "config" / "apps"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        path = target_dir / f"{app_id}.yaml"
        if path.exists():
            return

        skeleton = {
            "name": app_id.capitalize(),
            "package_name": app_package,
            "version": "1.0.0",
            "description": f"Auto-generated config for {app_package}",
            "xml_filter": [],
            "states": {},
            "selectors": {},
            "schemes": {}
        }
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(skeleton, f, sort_keys=False, allow_unicode=True)
            logger.info("Bootstrapped app config for %s at %s", app_package, path)
            # 刷新缓存
            cls.get_package_to_app_map(refresh=True)
        except Exception as exc:
            logger.error("Failed to bootstrap app config for %s: %s", app_package, exc)
