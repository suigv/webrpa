from __future__ import annotations

import logging
import os

from core.paths import project_root

logger = logging.getLogger(__name__)
_FALSE_VALUES = {"0", "false", "no", "off"}


def load_project_dotenv(*, override: bool = False) -> None:
    """Load project-root .env for direct app entrypoints when enabled."""
    raw_enabled = os.environ.get("MYT_LOAD_DOTENV", "0").strip().lower()
    if raw_enabled in _FALSE_VALUES:
        return

    env_path = project_root() / ".env"
    if not env_path.exists():
        return

    try:
        with env_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[7:].strip()
                if not key:
                    continue
                value = value.strip().strip("\"'")
                if override or key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to load project .env from %s: %s", env_path, exc)
