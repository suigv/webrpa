#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash scripts/setup_headless_browser.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  fonts-liberation \
  fonts-noto-color-emoji \
  libasound2 \
  libatk-bridge2.0-0 \
  libatk1.0-0 \
  libcups2 \
  libdbus-1-3 \
  libdrm2 \
  libgbm1 \
  libglib2.0-0 \
  libgtk-3-0 \
  libnspr4 \
  libnss3 \
  libu2f-udev \
  libx11-6 \
  libx11-xcb1 \
  libxcb1 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxkbcommon0 \
  libxrandr2 \
  xdg-utils

if command -v chromium >/dev/null 2>&1; then
  CHROME_BIN="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME_BIN="$(command -v chromium-browser)"
else
  apt-get install -y chromium || apt-get install -y chromium-browser
  if command -v chromium >/dev/null 2>&1; then
    CHROME_BIN="$(command -v chromium)"
  elif command -v chromium-browser >/dev/null 2>&1; then
    CHROME_BIN="$(command -v chromium-browser)"
  else
    echo "Chromium installation failed: no chromium binary found"
    exit 2
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  echo "Python venv missing at ${PROJECT_ROOT}/.venv. Create it first."
  exit 3
fi

"${PROJECT_ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${PROJECT_ROOT}/.venv/bin/pip" install DrissionPage DrissionGet

echo "Headless browser setup completed"
echo "CHROME_BIN=${CHROME_BIN}"
echo "Verify with: ${PROJECT_ROOT}/.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001"
echo "Then curl: http://127.0.0.1:8001/api/diagnostics/browser"
