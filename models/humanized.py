from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TARGET_STRATEGIES: Final[set[str]] = {"center", "center_bias", "random_inside"}
FALLBACK_POLICIES: Final[set[str]] = {"raw", "skip", "raise"}


@dataclass(frozen=True)
class HumanizedConfig:
    enabled: bool = True

    typing_delay_min: float = 0.04
    typing_delay_max: float = 0.18
    typo_probability: float = 0.03
    typo_delay_min: float = 0.04
    typo_delay_max: float = 0.12
    backspace_delay_min: float = 0.02
    backspace_delay_max: float = 0.08
    word_pause_probability: float = 0.04
    word_pause_min: float = 0.08
    word_pause_max: float = 0.24

    click_offset_x_min: int = -4
    click_offset_x_max: int = 4
    click_offset_y_min: int = -4
    click_offset_y_max: int = 4
    pre_click_pause_min: float = 0.02
    pre_click_pause_max: float = 0.10
    click_hold_min: float = 0.01
    click_hold_max: float = 0.05
    post_click_pause_min: float = 0.02
    post_click_pause_max: float = 0.08

    target_strategy: str = "center_bias"
    target_center_bias_probability: float = 0.85
    pre_hover_enabled: bool = True
    pre_hover_delay_min: float = 0.02
    pre_hover_delay_max: float = 0.08
    movement_jitter_probability: float = 0.05
    movement_overshoot_probability: float = 0.0

    move_duration_min: float = 0.20
    move_duration_max: float = 0.70
    move_steps_min: int = 8
    move_steps_max: int = 24

    fallback_policy: str = "raw"
    fallback_retry_count: int = 0
    random_seed: int | None = None

    def __post_init__(self) -> None:
        self._validate_probability("typo_probability", self.typo_probability)
        self._validate_probability("word_pause_probability", self.word_pause_probability)
        self._validate_probability(
            "target_center_bias_probability", self.target_center_bias_probability
        )
        self._validate_probability("movement_jitter_probability", self.movement_jitter_probability)
        self._validate_probability(
            "movement_overshoot_probability", self.movement_overshoot_probability
        )

        self._validate_range(
            "typing_delay_min", self.typing_delay_min, "typing_delay_max", self.typing_delay_max
        )
        self._validate_range(
            "typo_delay_min", self.typo_delay_min, "typo_delay_max", self.typo_delay_max
        )
        self._validate_range(
            "backspace_delay_min",
            self.backspace_delay_min,
            "backspace_delay_max",
            self.backspace_delay_max,
        )
        self._validate_range(
            "word_pause_min", self.word_pause_min, "word_pause_max", self.word_pause_max
        )

        self._validate_range(
            "click_offset_x_min",
            self.click_offset_x_min,
            "click_offset_x_max",
            self.click_offset_x_max,
        )
        self._validate_range(
            "click_offset_y_min",
            self.click_offset_y_min,
            "click_offset_y_max",
            self.click_offset_y_max,
        )
        self._validate_range(
            "pre_click_pause_min",
            self.pre_click_pause_min,
            "pre_click_pause_max",
            self.pre_click_pause_max,
        )
        self._validate_range(
            "click_hold_min", self.click_hold_min, "click_hold_max", self.click_hold_max
        )
        self._validate_range(
            "post_click_pause_min",
            self.post_click_pause_min,
            "post_click_pause_max",
            self.post_click_pause_max,
        )

        self._validate_range(
            "pre_hover_delay_min",
            self.pre_hover_delay_min,
            "pre_hover_delay_max",
            self.pre_hover_delay_max,
        )
        self._validate_range(
            "move_duration_min", self.move_duration_min, "move_duration_max", self.move_duration_max
        )
        self._validate_range(
            "move_steps_min", self.move_steps_min, "move_steps_max", self.move_steps_max
        )

        self._validate_non_negative("typing_delay_min", self.typing_delay_min)
        self._validate_non_negative("typing_delay_max", self.typing_delay_max)
        self._validate_non_negative("typo_delay_min", self.typo_delay_min)
        self._validate_non_negative("typo_delay_max", self.typo_delay_max)
        self._validate_non_negative("backspace_delay_min", self.backspace_delay_min)
        self._validate_non_negative("backspace_delay_max", self.backspace_delay_max)
        self._validate_non_negative("word_pause_min", self.word_pause_min)
        self._validate_non_negative("word_pause_max", self.word_pause_max)
        self._validate_non_negative("pre_click_pause_min", self.pre_click_pause_min)
        self._validate_non_negative("pre_click_pause_max", self.pre_click_pause_max)
        self._validate_non_negative("click_hold_min", self.click_hold_min)
        self._validate_non_negative("click_hold_max", self.click_hold_max)
        self._validate_non_negative("post_click_pause_min", self.post_click_pause_min)
        self._validate_non_negative("post_click_pause_max", self.post_click_pause_max)
        self._validate_non_negative("pre_hover_delay_min", self.pre_hover_delay_min)
        self._validate_non_negative("pre_hover_delay_max", self.pre_hover_delay_max)
        self._validate_non_negative("move_duration_min", self.move_duration_min)
        self._validate_non_negative("move_duration_max", self.move_duration_max)

        if self.move_steps_min < 1:
            raise ValueError("move_steps_min must be >= 1")
        if self.move_steps_max < 1:
            raise ValueError("move_steps_max must be >= 1")
        if self.fallback_retry_count < 0:
            raise ValueError("fallback_retry_count must be >= 0")

        if self.target_strategy not in TARGET_STRATEGIES:
            raise ValueError(f"target_strategy must be one of {sorted(TARGET_STRATEGIES)}")
        if self.fallback_policy not in FALLBACK_POLICIES:
            raise ValueError(f"fallback_policy must be one of {sorted(FALLBACK_POLICIES)}")

    @staticmethod
    def _validate_probability(name: str, value: float) -> None:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be within [0, 1]")

    @staticmethod
    def _validate_range(
        min_name: str, min_value: int | float, max_name: str, max_value: int | float
    ) -> None:
        if min_value > max_value:
            raise ValueError(f"{min_name} must be <= {max_name}")

    @staticmethod
    def _validate_non_negative(name: str, value: int | float) -> None:
        if value < 0:
            raise ValueError(f"{name} must be >= 0")


@dataclass(frozen=True)
class HumanizedWrapperConfig(HumanizedConfig):
    pass
