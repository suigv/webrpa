from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [
    "api",
    "core",
    "models",
    "common",
    "engine",
    "hardware_adapters",
    "ai_services",
    "plugins",
    "tests",
    "tools",
    "config",
]
PY_PATTERNS = [
    re.compile(r"\bfrom\s+tasks\b"),
    re.compile(r"\bimport\s+tasks\b"),
    re.compile(r"\bfrom\s+app\."),
    re.compile(r"\bimport\s+app\."),
    re.compile(r"\bmigrate_legacy_txt_to_json\b"),
    re.compile(r"\bENABLE_LEGACY_MIGRATION\b"),
]

DOC_PATTERNS = [
    re.compile(r"original repository"),
    re.compile(r"/home/suigv/文档/autorpc/app"),
]

DOC_FILES = [
    ROOT / "README.md",
]


def main() -> int:
    offenders = []
    for rel_dir in SCAN_DIRS:
        base = ROOT / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in PY_PATTERNS:
                if pattern.search(text):
                    offenders.append((str(path), pattern.pattern))

    for path in DOC_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in DOC_PATTERNS:
            if pattern.search(text):
                offenders.append((str(path), pattern.pattern))

    if offenders:
        print("Forbidden imports found:")
        for file_path, pattern in offenders:
            print(f"- {file_path}: {pattern}")
        return 1

    print("OK: no legacy imports found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
