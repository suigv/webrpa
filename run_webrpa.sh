#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
WebRPA 一键启动脚本（适配：API-only 后端 + Vite 前端 + JWT 可选）

默认（验收推荐）：
  - RPC=1（实机链路）
  - 队列=redis（若 redis 不可用会提示并回退为 memory）
  - 鉴权=jwt（若未设置 MYT_JWT_SECRET，会生成临时 secret/token 并打印）
  - 前端=dev（启动 web/ 的 Vite dev server，并设置 MYT_FRONTEND_URL）

用法：
  ./run_webrpa.sh [--rpc 0|1] [--queue redis|memory] [--auth jwt|disabled]
                 [--protect-openapi 0|1] [--frontend dev|none]
                 [--host 127.0.0.1] [--port 8001] [--detach] [--stop]

示例：
  # 纯 Web 回退（无设备）
  ./run_webrpa.sh --rpc 0

  # 关闭鉴权
  ./run_webrpa.sh --auth disabled

  # 只启动后端（不启前端 dev server）
  ./run_webrpa.sh --frontend none

  # 停止（按端口杀进程）
  ./run_webrpa.sh --stop
EOF
}

log() { echo ">>> $*"; }

API_HOST="${MYT_API_HOST:-127.0.0.1}"
API_PORT="${MYT_API_PORT:-8001}"
RPC_ENABLED="${MYT_ENABLE_RPC:-1}"
QUEUE_BACKEND="${MYT_TASK_QUEUE_BACKEND:-redis}"
AUTH_MODE="${MYT_AUTH_MODE:-jwt}"
PROTECT_OPENAPI="${MYT_AUTH_PROTECT_OPENAPI:-0}"
FRONTEND_MODE="${MYT_FRONTEND_MODE:-dev}"
DETACH=0
STOP_ONLY=0

FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="5173"

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --host) API_HOST="$2"; shift 2 ;;
    --port) API_PORT="$2"; shift 2 ;;
    --rpc) RPC_ENABLED="$2"; shift 2 ;;
    --queue) QUEUE_BACKEND="$2"; shift 2 ;;
    --auth) AUTH_MODE="$2"; shift 2 ;;
    --protect-openapi) PROTECT_OPENAPI="$2"; shift 2 ;;
    --frontend) FRONTEND_MODE="$2"; shift 2 ;;
    --detach) DETACH=1; shift 1 ;;
    --stop) STOP_ONLY=1; shift 1 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

export PYTHONPATH=.
export MYT_LOAD_DOTENV="${MYT_LOAD_DOTENV:-1}"
export MYT_API_HOST="$API_HOST"
export MYT_API_PORT="$API_PORT"
export MYT_ENABLE_RPC="$RPC_ENABLED"
export MYT_TASK_QUEUE_BACKEND="$QUEUE_BACKEND"
export MYT_AUTH_MODE="$AUTH_MODE"
export MYT_AUTH_PROTECT_OPENAPI="$PROTECT_OPENAPI"

if [ -f "$ROOT_DIR/.env" ] && [ "${MYT_LOAD_DOTENV}" != "0" ]; then
  log "加载 .env..."
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +a
fi

kill_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti tcp:"${port}" 2>/dev/null || true)"
    if [ -n "${pids}" ]; then
      log "结束占用端口 ${port} 的进程: ${pids}"
      kill -9 ${pids} >/dev/null 2>&1 || true
    fi
  else
    log "未检测到 lsof，跳过端口清理: ${port}"
  fi
}

if [ "${STOP_ONLY}" = "1" ]; then
  kill_port "${API_PORT}"
  kill_port "${FRONTEND_PORT}"
  exit 0
fi

log "清理残留端口进程..."
kill_port "${API_PORT}"
if [ "${FRONTEND_MODE}" = "dev" ]; then
  kill_port "${FRONTEND_PORT}"
fi

if [ "${QUEUE_BACKEND}" = "redis" ]; then
  if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli ping >/dev/null 2>&1; then
      log "未检测到 Redis，尝试启动（macOS: brew services）..."
      if [ "$(uname -s 2>/dev/null || true)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        brew services start redis >/dev/null 2>&1 || true
      fi
      if ! redis-cli ping >/dev/null 2>&1; then
        log "Redis 仍不可用：将队列回退为 memory（可用 --queue redis 强制并自行修复 Redis）"
        export MYT_TASK_QUEUE_BACKEND="memory"
      fi
    fi
  else
    log "未检测到 redis-cli：将队列回退为 memory"
    export MYT_TASK_QUEUE_BACKEND="memory"
  fi
fi

JWT_SECRET_FILE="/tmp/webrpa_jwt_secret"
JWT_TOKEN_FILE="/tmp/webrpa_jwt_token"

if [ "${MYT_AUTH_MODE}" = "jwt" ]; then
  if [ -z "${MYT_JWT_SECRET:-}" ]; then
    log "MYT_JWT_SECRET 未设置：生成临时 secret（仅用于本机验收/开发）"
    if [ -x "./.venv/bin/python" ]; then
      ./.venv/bin/python -c 'import secrets,pathlib; pathlib.Path("'"${JWT_SECRET_FILE}"'").write_text(secrets.token_urlsafe(48), encoding="utf-8")'
    else
      python3 -c 'import secrets,pathlib; pathlib.Path("'"${JWT_SECRET_FILE}"'").write_text(secrets.token_urlsafe(48), encoding="utf-8")'
    fi
    export MYT_JWT_SECRET="$(cat "${JWT_SECRET_FILE}")"
  else
    echo -n "${MYT_JWT_SECRET}" > "${JWT_SECRET_FILE}"
  fi

  if [ -x "./.venv/bin/python" ]; then
    MYT_JWT_SECRET="${MYT_JWT_SECRET}" ./.venv/bin/python tools/generate_jwt.py --sub operator --ttl-seconds 86400 > "${JWT_TOKEN_FILE}"
  else
    MYT_JWT_SECRET="${MYT_JWT_SECRET}" python3 tools/generate_jwt.py --sub operator --ttl-seconds 86400 > "${JWT_TOKEN_FILE}"
  fi
fi

BACKEND_LOG="/tmp/webrpa_backend_${API_PORT}.log"
FRONTEND_LOG="/tmp/webrpa_frontend_${FRONTEND_PORT}.log"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [ -n "${BACKEND_PID}" ] && ps -p "${BACKEND_PID}" >/dev/null 2>&1; then
    log "停止后端 PID=${BACKEND_PID}"
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${FRONTEND_PID}" ] && ps -p "${FRONTEND_PID}" >/dev/null 2>&1; then
    log "停止前端 PID=${FRONTEND_PID}"
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
}

if [ "${DETACH}" = "0" ]; then
  trap cleanup EXIT INT TERM
fi

if [ "${FRONTEND_MODE}" = "dev" ]; then
  if [ -f "${ROOT_DIR}/web/package.json" ] && command -v npm >/dev/null 2>&1; then
    export MYT_BACKEND_ORIGIN="http://${API_HOST}:${API_PORT}"
    export MYT_FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
    log "启动前端 (Vite): http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
    npm --prefix web run dev >"${FRONTEND_LOG}" 2>&1 &
    FRONTEND_PID="$!"
    log "前端 PID=${FRONTEND_PID} 日志=${FRONTEND_LOG}"
  else
    log "未检测到 npm 或 web/package.json：跳过启动前端。"
    log "你可以手动运行: cd web && npm install && npm run dev"
  fi
else
  log "前端模式=none：不启动 Vite dev server（生产请使用 Nginx 托管 web/dist）"
fi

log "启动后端 (FastAPI/uvicorn): http://${API_HOST}:${API_PORT}"
./.venv/bin/python -m uvicorn api.server:app --host "${API_HOST}" --port "${API_PORT}" --log-level info >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID="$!"
log "后端 PID=${BACKEND_PID} 日志=${BACKEND_LOG}"

log "健康检查: http://${API_HOST}:${API_PORT}/health"
if [ "${FRONTEND_MODE}" = "dev" ] && [ -n "${MYT_FRONTEND_URL:-}" ]; then
  log "控制台入口: http://${API_HOST}:${API_PORT}/web (307 -> ${MYT_FRONTEND_URL})"
else
  log "控制台入口: http://${API_HOST}:${API_PORT}/web (未设置 MYT_FRONTEND_URL 时将返回 501 提示)"
fi

if [ "${MYT_AUTH_MODE}" = "jwt" ]; then
  log "JWT 已启用：/api/* 需要 Authorization: Bearer <token>"
  log "本次 token（已写入 ${JWT_TOKEN_FILE}）："
  cat "${JWT_TOKEN_FILE}"
fi

if [ "${DETACH}" = "1" ]; then
  log "detach=1：进程已后台运行。停止：./run_webrpa.sh --stop"
  exit 0
fi

log "按 Ctrl+C 停止服务。"
wait
