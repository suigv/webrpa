from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
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
    ROOT / "AI_PROJECT_GUIDE.md",
    ROOT / "docs" / "migration-matrix.md",
]


def main() -> int:
    offenders = []
    for path in ROOT.rglob("*.py"):
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
