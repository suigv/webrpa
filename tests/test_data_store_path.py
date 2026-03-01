from new.core import data_store


def test_data_store_path_under_new_project():
    path = data_store._data_dir().replace("\\", "/")
    assert "/new/config/data" in path
