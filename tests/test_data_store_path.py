import json

from core import data_store


def test_data_store_path_under_new_project():
    path = data_store._data_dir().replace("\\", "/")
    assert "/config/data" in path


def test_write_text_preserves_valid_json_across_repeated_updates(monkeypatch, tmp_path):
    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    for idx in range(25):
        data_store.write_text("accounts", f"alpha-{idx}\nbeta-{idx}")
        payload = json.loads((tmp_path / "config" / "data" / "accounts.json").read_text(encoding="utf-8"))
        assert payload["type"] == "accounts"
        assert payload["lines"] == [f"alpha-{idx}", f"beta-{idx}"]
