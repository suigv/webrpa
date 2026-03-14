import pytest
from unittest.mock import MagicMock, patch
from engine.actions import ai_actions
from engine.models.runtime import ExecutionContext, ActionResult

def test_coerce_point_scaling():
    # 测试不同模式下的坐标转换
    # 场景：截图是 540x960，但物理设备是 1080x1920
    # 我们希望无论是 norm_1000 还是 norm_1，都应该映射到 1080x1920 物理空间
    width, height = 1080, 1920
    
    # 1. Pixel 模式 (不缩放)
    x, y = ai_actions._coerce_point(100, 200, width=width, height=height, coord_mode="pixel", clamp=True)
    assert x == 100
    assert y == 200
    
    # 2. norm_1000 模式
    # 500/1000 * 1080 = 540
    # 500/1000 * 1920 = 960
    x, y = ai_actions._coerce_point(500, 500, width=width, height=height, coord_mode="norm_1000", clamp=True)
    assert x == 540
    assert y == 960
    
    # 3. Normalized 模式 (0-1)
    x, y = ai_actions._coerce_point(0.5, 0.5, width=width, height=height, coord_mode="norm_1", clamp=True)
    assert x == 540
    assert y == 960

def test_locate_point_with_physical_resolution():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}
    
    # 彻底 mock 掉 evaluate，避免任何真实的 provider 初始化
    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        mock_capture.return_value = ActionResult(
            ok=True,
            data={
                "save_path": "/tmp/test.png",
                "screen_width": 540,
                "screen_height": 960,
                "physical_width": 1080, 
                "physical_height": 1920
            }
        )
        
        # 直接 mock ai_actions 模块中的 LLMClient 引用，并确保其 evaluate 返回正确 mock
        mock_client_instance = MagicMock()
        mock_response = MagicMock(ok=True, output_text='{"x": 500, "y": 500}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response
        
        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            res = ai_actions.locate_point({"prompt": "test", "coord_mode": "norm_1000"}, mock_context)
            
            assert res.ok
            assert res.data["x"] == 540
            assert res.data["y"] == 960
            assert res.data["screen_width"] == 1080
            assert res.data["screen_height"] == 1920
