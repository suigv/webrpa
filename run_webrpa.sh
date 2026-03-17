#!/bin/bash

# WebRPA 启动守卫脚本
echo "=== 正在准备启动 WebRPA 服务 (Port: 8001) ==="

# 1. 确保目录正确
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 2. 导出关键环境变量
export PYTHONPATH=.
export MYT_LOAD_DOTENV=1
# 注：多数“非敏”系统配置在 config/system.yaml 中维护；环境变量仍可用于覆盖（例如 MYT_ENABLE_RPC=0 / MYT_AUTH_MODE=jwt）。
export MYT_API_PORT=8001
export MYT_TASK_QUEUE_BACKEND=redis

# 3. 从 .env 文件加载敏感配置
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

# 3. 清理旧进程（尽量只清理占用本端口的进程）
echo ">>> 清理残留进程..."
API_PORT="${MYT_API_PORT:-8001}"
if command -v lsof >/dev/null 2>&1; then
    PIDS="$(lsof -ti tcp:"${API_PORT}" 2>/dev/null || true)"
    if [ -n "${PIDS}" ]; then
        echo ">>> 结束占用端口 ${API_PORT} 的进程: ${PIDS}"
        kill -9 ${PIDS} >/dev/null 2>&1 || true
    fi
else
    pkill -f "uvicorn api.server:app" >/dev/null 2>&1 || true
fi

# 4. 检查 Redis
if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli ping &> /dev/null; then
        echo "警告：未检测到 Redis 服务，尝试通过 brew 启动..."
        if command -v brew >/dev/null 2>&1; then
            brew services start redis || echo "错误：无法启动 Redis，请手动检查！"
        else
            echo "错误：未检测到 brew，请手动启动 Redis。"
        fi
    fi
else
    echo "警告：未检测到 redis-cli，跳过 Redis 自检。"
fi

# 5. 正式启动
echo ">>> 服务启动中... 请保持此终端窗口不要关闭！"
echo ">>> 后端健康检查: http://127.0.0.1:${API_PORT}/health"
if [ -n "${MYT_FRONTEND_URL:-}" ]; then
    echo ">>> 控制台入口: http://127.0.0.1:${API_PORT}/web (将 307 重定向到 MYT_FRONTEND_URL=${MYT_FRONTEND_URL})"
else
    echo ">>> 控制台(开发): cd web && npm install && npm run dev  (访问 http://127.0.0.1:5173/)"
    echo ">>> 或设置 MYT_FRONTEND_URL=http://127.0.0.1:5173 后访问: http://127.0.0.1:${API_PORT}/web"
fi
echo "------------------------------------------------"

./.venv/bin/python -m uvicorn api.server:app --host 0.0.0.0 --port "${API_PORT}" --log-level info
