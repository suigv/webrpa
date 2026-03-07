from pathlib import Path
import re


TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s")


def test_plugin_manifests_do_not_repeat_top_level_keys():
    plugins_root = Path(__file__).resolve().parents[1] / "plugins"
    manifest_paths = sorted(plugins_root.glob("*/manifest.yaml"))

    assert manifest_paths, "expected plugin manifests to exist"

    for manifest_path in manifest_paths:
        seen: set[str] = set()
        duplicates: list[str] = []
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.startswith((" ", "\t", "-")):
                continue
            match = TOP_LEVEL_KEY.match(line)
            if not match:
                continue
            key = match.group(1)
            if key in seen:
                duplicates.append(key)
                continue
            seen.add(key)

        assert not duplicates, f"{manifest_path} repeats top-level key(s): {', '.join(sorted(set(duplicates)))}"
