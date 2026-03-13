#!/bin/bash

# WebRPA 启动守卫脚本
echo "=== 正在准备启动 WebRPA 服务 (Port: 8001) ==="

# 1. 确保目录正确
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 2. 导出关键环境变量
export PYTHONPATH=.
export MYT_LOAD_DOTENV=1
export MYT_ENABLE_RPC=1
export MYT_ENABLE_VLM=1
export MYT_API_PORT=8001
export MYT_TASK_QUEUE_BACKEND=redis

# 3. 从 .env 文件加载敏感配置
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

# 3. 强力清理旧进程
echo ">>> 清理残留进程..."
pkill -9 -f uvicorn || true

# 4. 检查 Redis
if ! redis-cli ping &> /dev/null; then
    echo "警告：未检测到 Redis 服务，尝试通过 brew 启动..."
    brew services start redis || echo "错误：无法启动 Redis，请手动检查！"
fi

# 5. 正式启动
echo ">>> 服务启动中... 请保持此终端窗口不要关闭！"
echo ">>> 访问地址: http://127.0.0.1:8001/web"
echo "------------------------------------------------"

./.venv/bin/python -m uvicorn api.server:app --host 0.0.0.0 --port 8001 --log-level info
