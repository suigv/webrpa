from unittest.mock import MagicMock, patch

from engine.actions.ui_actions import click
from engine.models.runtime import ExecutionContext
from models.humanized import HumanizedConfig


def test_native_click_applies_humanized_offsets():
    """验证原生 UI 点击是否正确应用了拟人化偏移。"""

    # 1. 准备 Mock 环境
    mock_rpc = MagicMock()
    # 模拟 rpc.touchDown 和 touchUp 成功
    mock_rpc.touchDown.return_value = True
    mock_rpc.touchUp.return_value = True

    # 2. 构造带配置的上下文
    # 故意设置一个较大的偏移范围以便观察效果
    config = HumanizedConfig(
        enabled=True,
        click_offset_x_min=-10,
        click_offset_x_max=10,
        click_offset_y_min=-10,
        click_offset_y_max=10,
        pre_click_pause_min=0,
        pre_click_pause_max=0,  # 禁用停顿以便快速运行测试
    )

    context = ExecutionContext(payload={})
    # 注入测试用的 helper
    from engine.humanized_helper import HumanizedHelper

    context._humanized = HumanizedHelper(config)

    # 3. 拦截 _get_rpc 以注入我们的 Mock
    with (
        patch("engine.actions.ui_actions._get_rpc", return_value=(mock_rpc, None)),
        patch("engine.actions.ui_actions._close_rpc"),
    ):
        target_x, target_y = 500, 500
        captured_coords = []

        # 执行 10 次点击
        for _ in range(10):
            params = {"x": target_x, "y": target_y}
            click(params, context)

            # 获取最后一次调用的参数
            args, _ = mock_rpc.touchDown.call_args
            # touchDown(finger_id, x, y)
            captured_coords.append((args[1], args[2]))

        # 4. 验证结果
        print(f"\nCaptured Coords: {captured_coords}")

        # 验证是否有偏移（如果所有坐标都一样，说明拟人化失效）
        unique_coords = set(captured_coords)
        assert len(unique_coords) > 1, "Click coordinates should be randomized"

        # 验证偏移是否在范围内 (+/- 10)
        for cx, cy in captured_coords:
            assert abs(cx - target_x) <= 10
            assert abs(cy - target_y) <= 10

        # 验证是否调用了物理按压模拟 (TouchDown -> TouchUp)
        assert mock_rpc.touchDown.called
        assert mock_rpc.touchUp.called


def test_native_click_respects_disabled_config():
    """验证当拟人化禁用时，坐标是否保持原样。"""
    mock_rpc = MagicMock()
    mock_rpc.touchDown.return_value = True
    mock_rpc.touchUp.return_value = True

    config = HumanizedConfig(enabled=False)
    context = ExecutionContext(payload={})
    from engine.humanized_helper import HumanizedHelper

    context._humanized = HumanizedHelper(config)

    with (
        patch("engine.actions.ui_actions._get_rpc", return_value=(mock_rpc, None)),
        patch("engine.actions.ui_actions._close_rpc"),
    ):
        target_x, target_y = 500, 500
        params = {"x": target_x, "y": target_y}
        click(params, context)

        args, _ = mock_rpc.touchDown.call_args
        # 禁用时，坐标应保持 500, 500
        assert args[1] == 500
        assert args[2] == 500
