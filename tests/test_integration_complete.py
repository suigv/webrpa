import importlib


def _load_action_registry_module():
    for name in ("engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


def test_complete_registry_integration(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()
    names = set(reg.names)
    assert "ui.click" in names
    assert "ui.input_text" in names
    assert "ui.swipe" in names
    assert "ui.key_press" in names
    assert "app.open" in names
    assert "app.stop" in names
    assert "device.exec" in names
    assert "device.capture_raw" in names
    assert "device.capture_compressed" in names
    assert "device.get_display_rotate" in names
    assert "ui.selector_find_nodes" in names
    assert "ui.selector_free" in names
    assert "ui.selector_get_nodes_size" in names
    assert "ui.selector_get_node_by_index" in names
    assert "ui.selector_free_nodes" in names
    assert "ui.node_click" in names
    assert "ui.node_long_click" in names
    assert "ui.node_get_json" in names
    assert "ui.node_get_text" in names
    assert "ui.node_get_desc" in names
    assert "ui.node_get_package" in names
    assert "ui.node_get_class" in names
    assert "ui.node_get_id" in names
    assert "ui.node_get_bound" in names
    assert "ui.node_get_bound_center" in names
    assert "ui.node_get_parent" in names
    assert "ui.node_get_child_count" in names
    assert "ui.node_get_child" in names
