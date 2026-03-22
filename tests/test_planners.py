from engine.planners import PlannerInput, StructuredPlanner


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.ok = True
        self.output_text = output_text
        self.request_id = "req-1"
        self.provider = "fake"
        self.model = "fake-model"
        self.structured_state = {"mode": "structured"}


class _FakeLlmClient:
    def evaluate(self, request, runtime_config=None):  # noqa: ANN001
        _ = (request, runtime_config)
        return _FakeResponse('{"done": false, "action": "ui.click", "params": {"x": 1, "y": 2}}')


class _FakeRuntime:
    def __init__(self) -> None:
        self._llm_client_factory = lambda: _FakeLlmClient()

    @staticmethod
    def _wants_vlm(_modalities):
        return False

    @staticmethod
    def _llm_request_trace(request, *, runtime_config):  # noqa: ANN001
        _ = runtime_config
        return {"prompt": request.prompt}

    @staticmethod
    def _llm_response_trace(response):  # noqa: ANN001
        return {"ok": response.ok, "output_text": response.output_text}


def test_structured_planner_no_longer_requires_legacy_plan_method() -> None:
    planner = StructuredPlanner(_FakeRuntime())

    result = planner.plan(
        PlannerInput(
            goal="tap button",
            step_index=1,
            allowed_actions=["ui.click"],
            observation={"state_id": "account"},
            last_action=None,
            fallback_enabled=False,
            fallback_reason="",
            fallback_evidence={},
            fallback_modalities=[],
            system_prompt="",
            llm_runtime={},
            planner_inputs={},
            planner_artifact={"goal_text": "tap button", "advanced_prompt": "be careful"},
        )
    )

    assert result.ok is True
    assert result.action == "ui.click"
    assert result.params == {"x": 1, "y": 2}
    assert result.diagnostics["request"]["prompt"]
    assert result.planner_artifact["advanced_prompt"] == "be careful"
