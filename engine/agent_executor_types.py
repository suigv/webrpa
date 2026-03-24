from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ai_services.llm_client import LLMRequest


class LLMClientLike(Protocol):
    def evaluate(
        self, request: LLMRequest, *, runtime_config: dict[str, object] | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class AgentExecutorConfig:
    goal: str
    expected_state_ids: list[str]
    allowed_actions: list[str]
    max_steps: int
    allow_step_budget_extension: bool
    stagnant_limit: int
    system_prompt: str
    llm_runtime: dict[str, object]
    planner_inputs: dict[str, object]
    planner_artifact: dict[str, object]
    fallback_modalities: list[str]
    observation_params: dict[str, object]
