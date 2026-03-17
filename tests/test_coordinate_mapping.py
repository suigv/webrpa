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
            # 使用 norm_1000 模式，AI 返回 500x500
            # 内部 coercion 之后在 540x960 图像上应为 x=270, y=480
            # 物理屏幕上有重新映射: x = (270 / 540) * 1080 = 540
            # y = (480 / 960) * 1920 = 960
            res = ai_actions.locate_point({"prompt": "test", "coord_mode": "norm_1000"}, mock_context)
            
            assert res.ok
            assert res.data["x"] == 540
            assert res.data["y"] == 960
            assert res.data["screen_width"] == 540
            assert res.data["screen_height"] == 960
            assert res.data["physical_width"] == 1080
            assert res.data["physical_height"] == 1920

def test_locate_point_pixel_mode_preserves_accuracy():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}
    
    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        # LLM 看到的是 540x960
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
        
        mock_client_instance = MagicMock()
        # VLM 指定点击真实图片的下方一点： x:270, y:800 (总高960)
        mock_response = MagicMock(ok=True, output_text='{"x": 270, "y": 800}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response
        
        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            # 默认是 coord_mode="pixel"
            res = ai_actions.locate_point({"prompt": "test"}, mock_context)
            
            assert res.ok
            # x = (270 / 540) * 1080 = 540
            assert res.data["x"] == 540
            # y = (800 / 960) * 1920 = 1600
            assert res.data["y"] == 1600
            
            # Request 中应该发送真实的图片尺寸：
            # LLMRequest(...) 会保留真实的 image 的分辨率进行 prompt 拼接
            request_args = mock_client_instance.evaluate.call_args[0][0]
            assert "Image size: 540x960" in request_args.prompt

def test_locate_point_landscape_orientation():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}
    
    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        # LLM看到的是横屏 960x540
        # 物理设备尺寸(如 wm size 所报) 依然通常是固定的 1080x1920，而此时物理环境实质上翻转了。
        mock_capture.return_value = ActionResult(
            ok=True,
            data={
                "save_path": "/tmp/test.png",
                "screen_width": 960,
                "screen_height": 540,
                "physical_width": 1080, 
                "physical_height": 1920
            }
        )
        
        mock_client_instance = MagicMock()
        # VLM 指定点击真实截图中下方中间： x:480, y:500 (总宽960，总高540)
        mock_response = MagicMock(ok=True, output_text='{"x": 480, "y": 500}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response
        
        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            res = ai_actions.locate_point({"prompt": "test", "coord_mode": "pixel"}, mock_context)
            
            assert res.ok
            # system detected orientation mismatch
            # original physics: W:1080, H:1920 => Target flipped: W:1920, H:1080 (since screen is landscape)
            # x = (480 / 960) * 1920 = 960
            assert res.data["x"] == 960
            # y = (500 / 540) * 1080 = 1000
            assert res.data["y"] == 1000


def test_locate_point_accepts_instruction_alias():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}

    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        mock_capture.return_value = ActionResult(
            ok=True,
            data={
                "save_path": "/tmp/test.png",
                "screen_width": 540,
                "screen_height": 960,
            },
        )

        mock_client_instance = MagicMock()
        mock_response = MagicMock(ok=True, output_text='{"x": 10, "y": 20}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response

        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            res = ai_actions.locate_point({"instruction": "find login button"}, mock_context)

            assert res.ok
            request_args = mock_client_instance.evaluate.call_args[0][0]
            assert "find login button" in request_args.prompt


def test_locate_point_accepts_text_alias():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}

    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        mock_capture.return_value = ActionResult(
            ok=True,
            data={
                "save_path": "/tmp/test.png",
                "screen_width": 540,
                "screen_height": 960,
            },
        )

        mock_client_instance = MagicMock()
        mock_response = MagicMock(ok=True, output_text='{"x": 10, "y": 20}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response

        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            res = ai_actions.locate_point({"text": "find password field"}, mock_context)

            assert res.ok
            request_args = mock_client_instance.evaluate.call_args[0][0]
            assert "find password field" in request_args.prompt


def test_locate_point_accepts_description_alias():
    mock_context = MagicMock()
    mock_context.device_id = 1
    mock_context.runtime = {"llm": {"api_key": "test"}}

    with patch("engine.actions.ai_actions.capture_compressed") as mock_capture:
        mock_capture.return_value = ActionResult(
            ok=True,
            data={
                "save_path": "/tmp/test.png",
                "screen_width": 540,
                "screen_height": 960,
            },
        )

        mock_client_instance = MagicMock()
        mock_response = MagicMock(ok=True, output_text='{"x": 10, "y": 20}', model="test", error=None)
        mock_client_instance.evaluate.return_value = mock_response

        with patch("engine.actions.ai_actions.LLMClient", return_value=mock_client_instance):
            res = ai_actions.locate_point({"description": "find email field"}, mock_context)

            assert res.ok
            request_args = mock_client_instance.evaluate.call_args[0][0]
            assert "find email field" in request_args.prompt
