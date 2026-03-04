# pyright: reportMissingImports=false
from new.hardware_adapters.browser_client import HumanizedWrapper
from new.models.humanized import HumanizedWrapperConfig


class _FakeRect:
    def __init__(self, location=(100, 200), size=(80, 40)):
        self.location = location
        self.size = size


class _FakeElement:
    def __init__(self):
        self.rect = _FakeRect()
        self.cleared = 0
        self.clicked = 0
        self.fallback_input_payload = None

    def clear(self):
        self.cleared += 1

    def click(self):
        self.clicked += 1

    def input(self, text):
        self.fallback_input_payload = text


class _FakeActions:
    def __init__(self):
        self.curr_x = 0
        self.curr_y = 0
        self.moves = []
        self.types = []
        self.clicks = 0

    def move_to(self, loc, duration=0.5):
        self.curr_x, self.curr_y = loc
        self.moves.append((loc, duration))
        return self

    def click(self):
        self.clicks += 1
        return self

    def type(self, text):
        self.types.append(text)
        return self


class _DownUpActions:
    def __init__(self):
        self.curr_x = 0
        self.curr_y = 0
        self.moves = []
        self.down_calls = 0
        self.up_calls = 0

    def move_to(self, loc, duration=0.5):
        self.curr_x, self.curr_y = loc
        self.moves.append((loc, duration))
        return self

    def down(self):
        self.down_calls += 1
        return self

    def up(self):
        self.up_calls += 1
        return self


class _NoTypeActions:
    def __init__(self):
        self.curr_x = 0
        self.curr_y = 0


class _NoMoveActions:
    def __init__(self):
        self.curr_x = 0
        self.curr_y = 0


class _FakePage:
    def __init__(self):
        self._ele = _FakeElement()
        self.actions = _FakeActions()

    def ele(self, _selector):
        return self._ele


class _NoActionsPage:
    def __init__(self):
        self._ele = _FakeElement()

    def ele(self, _selector):
        return self._ele


class _ViewportPage(_FakePage):
    def __init__(self, viewport_size=(120, 220)):
        super().__init__()
        self.viewport_size = viewport_size


class _DownUpPage(_FakePage):
    def __init__(self):
        super().__init__()
        self.actions = _DownUpActions()


class _NoTypePage(_FakePage):
    def __init__(self):
        super().__init__()
        self.actions = _NoTypeActions()


class _NoMovePage(_FakePage):
    def __init__(self):
        super().__init__()
        self.actions = _NoMoveActions()


class _MalformedRectElement(_FakeElement):
    def __init__(self):
        super().__init__()
        self.rect = _FakeRect(location=("bad", None), size=(80, 40))


class _MalformedRectPage(_FakePage):
    def __init__(self):
        super().__init__()
        self._ele = _MalformedRectElement()


def test_humanized_config_validation_probability_bounds():
    try:
        HumanizedWrapperConfig(typo_probability=1.2)
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_humanized_config_defaults_are_stable():
    cfg = HumanizedWrapperConfig()

    assert cfg.target_strategy == "center_bias"
    assert cfg.fallback_policy == "raw"
    assert cfg.random_seed is None
    assert cfg.move_steps_min >= 1
    assert cfg.move_steps_max >= cfg.move_steps_min


def test_humanized_config_validation_rejects_invalid_strategy_and_policy():
    try:
        HumanizedWrapperConfig(target_strategy="outside")
        assert False, "expected ValueError"
    except ValueError:
        assert True

    try:
        HumanizedWrapperConfig(fallback_policy="unsupported")
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_humanized_config_validation_rejects_invalid_step_bounds():
    try:
        HumanizedWrapperConfig(move_steps_min=0)
        assert False, "expected ValueError"
    except ValueError:
        assert True

    try:
        HumanizedWrapperConfig(move_steps_min=3, move_steps_max=2)
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_humanized_input_typo_and_backspace_flow():
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=1,
        typo_probability=1.0,
        typing_delay_min=0,
        typing_delay_max=0,
        typo_delay_min=0,
        typo_delay_max=0,
        backspace_delay_min=0,
        backspace_delay_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)
    object.__setattr__(cfg, "enable_typo_simulation", True)
    ele = wrapper.ele("#input")

    ele.input("ab")

    assert len(page.actions.types) >= 6
    assert "\b" in page.actions.types


def test_humanized_input_typo_stub_is_disabled_by_default():
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=1,
        typo_probability=1.0,
        typing_delay_min=0,
        typing_delay_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)

    wrapper.ele("#input").input("ab")

    assert page.actions.types == ["a", "b"]


def test_humanized_input_adds_word_boundary_pauses(monkeypatch):
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=2,
        typing_delay_min=0.01,
        typing_delay_max=0.01,
        word_pause_probability=1.0,
        word_pause_min=0.2,
        word_pause_max=0.2,
        typo_probability=0.0,
    )
    sleeps = []

    def _record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("new.hardware_adapters.browser_client.time.sleep", _record_sleep)

    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#input").input("ab c!")

    # 5 per-char typing sleeps + 2 boundary pauses (b->space, c->!).
    assert sleeps == [0.01, 0.01, 0.01, 0.2, 0.01, 0.01, 0.2]


def test_humanized_click_uses_actions_move_to_not_raw_click():
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=1,
        move_steps_min=3,
        move_steps_max=3,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0,
        click_hold_max=0,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)
    ele = wrapper.ele("#btn")

    ele.click()

    assert page.actions.clicks == 1
    assert len(page.actions.moves) == 3
    assert page._ele.clicked == 0


def test_humanized_fallback_without_actions_uses_raw_element_methods():
    page = _NoActionsPage()
    wrapper = HumanizedWrapper(page, HumanizedWrapperConfig())
    ele = wrapper.ele("#x")

    ele.input("hello")
    ele.click()

    assert page._ele.fallback_input_payload == "hello"
    assert page._ele.clicked == 1


def test_humanized_input_falls_back_when_actions_missing_type_capability():
    page = _NoTypePage()
    wrapper = HumanizedWrapper(page, HumanizedWrapperConfig())

    wrapper.ele("#x").input("hello")

    assert page._ele.fallback_input_payload == "hello"


def test_humanized_click_falls_back_when_actions_missing_move_to_capability():
    page = _NoMovePage()
    wrapper = HumanizedWrapper(page, HumanizedWrapperConfig())

    wrapper.ele("#x").click()

    assert page._ele.clicked == 1


def test_humanized_click_malformed_geometry_with_skip_policy_is_noop():
    page = _MalformedRectPage()
    cfg = HumanizedWrapperConfig(fallback_policy="skip")
    wrapper = HumanizedWrapper(page, cfg)

    wrapper.ele("#x").click()

    assert page._ele.clicked == 0


def test_humanized_click_fallback_policy_raise_propagates_failure():
    page = _NoMovePage()
    wrapper = HumanizedWrapper(page, HumanizedWrapperConfig(fallback_policy="raise"))

    try:
        wrapper.ele("#x").click()
        assert False, "expected RuntimeError"
    except RuntimeError:
        assert True


def test_humanized_input_fallback_policy_raise_propagates_failure():
    page = _NoTypePage()
    wrapper = HumanizedWrapper(page, HumanizedWrapperConfig(fallback_policy="raise"))

    try:
        wrapper.ele("#x").input("hello")
        assert False, "expected RuntimeError"
    except RuntimeError:
        assert True


def test_humanized_click_random_inside_clamps_to_element_bounds():
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=7,
        target_strategy="random_inside",
        click_offset_x_min=-1000,
        click_offset_x_max=1000,
        click_offset_y_min=-1000,
        click_offset_y_max=1000,
        move_steps_min=1,
        move_steps_max=1,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0,
        click_hold_max=0,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#btn").click()

    target_x, target_y = page.actions.moves[-1][0]
    assert 100 <= target_x <= 179
    assert 200 <= target_y <= 239


def test_humanized_click_center_strategy_clamps_to_viewport_intersection():
    page = _ViewportPage(viewport_size=(120, 220))
    cfg = HumanizedWrapperConfig(
        random_seed=1,
        target_strategy="center",
        click_offset_x_min=0,
        click_offset_x_max=0,
        click_offset_y_min=0,
        click_offset_y_max=0,
        move_steps_min=1,
        move_steps_max=1,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0,
        click_hold_max=0,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#btn").click()

    target_x, target_y = page.actions.moves[-1][0]
    assert 100 <= target_x <= 119
    assert 200 <= target_y <= 219


def test_humanized_click_jitter_and_overshoot_stay_within_viewport_bounds():
    page = _ViewportPage(viewport_size=(120, 220))
    cfg = HumanizedWrapperConfig(
        random_seed=5,
        target_strategy="center",
        click_offset_x_min=0,
        click_offset_x_max=0,
        click_offset_y_min=0,
        click_offset_y_max=0,
        move_steps_min=2,
        move_steps_max=2,
        movement_jitter_probability=1.0,
        movement_overshoot_probability=1.0,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0,
        click_hold_max=0,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )
    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#btn").click()

    assert page.actions.clicks == 1
    assert len(page.actions.moves) >= 2
    for (x, y), _duration in page.actions.moves:
        assert 0 <= x <= 119
        assert 0 <= y <= 219


def test_humanized_click_seeded_random_target_is_deterministic():
    def _click_with_seed(seed):
        page = _FakePage()
        cfg = HumanizedWrapperConfig(
            random_seed=seed,
            target_strategy="random_inside",
            click_offset_x_min=-3,
            click_offset_x_max=3,
            click_offset_y_min=-3,
            click_offset_y_max=3,
            move_steps_min=1,
            move_steps_max=1,
            pre_hover_enabled=False,
            pre_click_pause_min=0,
            pre_click_pause_max=0,
            click_hold_min=0,
            click_hold_max=0,
            post_click_pause_min=0,
            post_click_pause_max=0,
        )
        HumanizedWrapper(page, cfg).ele("#btn").click()
        return page.actions.moves[-1][0]

    first = _click_with_seed(123)
    second = _click_with_seed(123)
    third = _click_with_seed(124)

    assert first == second
    assert first != third
    assert 100 <= first[0] <= 179
    assert 200 <= first[1] <= 239


def test_humanized_click_applies_pre_hover_and_cadence_delays(monkeypatch):
    page = _FakePage()
    cfg = HumanizedWrapperConfig(
        random_seed=3,
        move_steps_min=1,
        move_steps_max=1,
        pre_hover_enabled=True,
        pre_hover_delay_min=0.11,
        pre_hover_delay_max=0.11,
        pre_click_pause_min=0.12,
        pre_click_pause_max=0.12,
        click_hold_min=0.13,
        click_hold_max=0.13,
        post_click_pause_min=0.14,
        post_click_pause_max=0.14,
    )
    sleeps = []

    def _record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("new.hardware_adapters.browser_client.time.sleep", _record_sleep)

    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#btn").click()

    assert page.actions.clicks == 1
    assert len(page.actions.moves) == 2
    assert page.actions.moves[-1][1] == 0.11
    assert sleeps == [0.12, 0.14]


def test_humanized_click_uses_down_up_when_click_method_unavailable(monkeypatch):
    page = _DownUpPage()
    cfg = HumanizedWrapperConfig(
        random_seed=4,
        move_steps_min=1,
        move_steps_max=1,
        pre_hover_enabled=False,
        pre_click_pause_min=0,
        pre_click_pause_max=0,
        click_hold_min=0.2,
        click_hold_max=0.2,
        post_click_pause_min=0,
        post_click_pause_max=0,
    )
    sleeps = []

    def _record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("new.hardware_adapters.browser_client.time.sleep", _record_sleep)

    wrapper = HumanizedWrapper(page, cfg)
    wrapper.ele("#btn").click()

    assert page.actions.down_calls == 1
    assert page.actions.up_calls == 1
    assert sleeps == [0.2]
