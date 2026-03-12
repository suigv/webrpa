from __future__ import annotations

import random
import time
from typing import Any, List, Tuple

from models.humanized import HumanizedConfig


class HumanizedHelper:
    """全平台通用的拟人化行为计算器。只负责逻辑计算，不负责执行。"""

    def __init__(self, config: HumanizedConfig, seed: Any = None) -> None:
        self.config = config
        self._rng = random.Random(seed)

    def apply_click_offset(
        self,
        x: int,
        y: int,
        bounds: Tuple[int, int, int, int] | None = None,
    ) -> Tuple[int, int]:
        """计算带随机偏移的点击坐标。

        bounds: 可选的元素边界 (x_min, y_min, x_max, y_max)，
                有边界时将偏移后坐标 clamp 到元素内，避免偏出范围。
        """
        if not self.config.enabled:
            return x, y

        offset_x = self._rng.randint(self.config.click_offset_x_min, self.config.click_offset_x_max)
        offset_y = self._rng.randint(self.config.click_offset_y_min, self.config.click_offset_y_max)
        new_x = x + offset_x
        new_y = y + offset_y

        if bounds is not None:
            x_min, y_min, x_max, y_max = bounds
            new_x = max(x_min, min(new_x, x_max))
            new_y = max(y_min, min(new_y, y_max))

        return new_x, new_y

    def get_typing_sequence(self, text: str) -> List[Tuple[str, float]]:
        """将文本拆分为带延迟的按键序列。"""
        if not self.config.enabled:
            return [(text, 0.0)]

        sequence = []
        for char in text:
            # 基础打字延迟
            delay = self._rng.uniform(self.config.typing_delay_min, self.config.typing_delay_max)
            
            # 单词间的额外停顿
            if char == " " and self._rng.random() < self.config.word_pause_probability:
                delay += self._rng.uniform(self.config.word_pause_min, self.config.word_pause_max)
            
            sequence.append((char, delay))
        return sequence

    def sleep_before_click(self) -> None:
        """点击前的心理停顿。"""
        if self.config.enabled:
            pause = self._rng.uniform(self.config.pre_click_pause_min, self.config.pre_click_pause_max)
            time.sleep(pause)

    def sleep_after_click(self) -> None:
        """点击后的确认停顿。"""
        if self.config.enabled:
            pause = self._rng.uniform(self.config.post_click_pause_min, self.config.post_click_pause_max)
            time.sleep(pause)

    def get_click_hold_time(self) -> float:
        """按下按钮的持续时间（模拟物理按压）。"""
        if not self.config.enabled:
            return 0.01
        return self._rng.uniform(self.config.click_hold_min, self.config.click_hold_max)
