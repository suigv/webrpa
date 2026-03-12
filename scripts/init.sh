#!/bin/bash
set -e

echo "=== WebRPA 开发环境初始化 ==="

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "错误：未安装 uv，请先安装: https://docs.astral.sh/uv/"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    uv venv --python 3.11
fi

# 安装依赖
echo "安装项目依赖..."
uv pip install -e ".[dev]"

# 创建必要目录
echo "创建运行时目录..."
mkdir -p config/data
mkdir -p logs

# 检查配置文件
if [ ! -f "config/devices.json" ]; then
    echo "创建设备配置模板..."
    cat > config/devices.json << 'JSON'
{
  "devices": []
}
JSON
fi

echo ""
echo "=== 初始化完成 ==="
echo ""
echo "启动开发服务器:"
echo "  uv run uvicorn api.server:app --reload --port 8001"
echo ""
echo "启动生产服务器:"
echo "  MYT_API_PORT=8001 uv run python api/server.py"
echo ""
echo "运行测试:"
echo "  uv run pytest"
echo ""
echo "代码检查:"
echo "  uv run ruff check ."
