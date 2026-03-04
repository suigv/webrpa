import importlib


def _load_action_registry_module():
    for name in ("new.engine.action_registry", "engine.action_registry"):
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
