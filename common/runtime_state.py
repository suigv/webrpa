import os
from typing import Dict, List

from new.common.config_manager import cfg


def _safe_remove(path: str) -> bool:
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except Exception:
        return False
    return False


def reset_runtime_state() -> Dict[str, object]:
    removed_files: List[str] = []
    failed_files: List[str] = []

    log_dir = cfg.log_dir
    os.makedirs(log_dir, exist_ok=True)
    for name in os.listdir(log_dir):
        path = os.path.join(log_dir, name)
        if not os.path.isfile(path):
            continue
        if _safe_remove(path):
            removed_files.append(name)
        else:
            failed_files.append(name)

    return {
        "removed_count": len(removed_files),
        "removed_files": removed_files,
        "failed_count": len(failed_files),
        "failed_files": failed_files,
    }
