import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# 基础配置
PORT = 8001
ROOT_DIR = Path(__file__).parent.absolute()
sys.path.append(str(ROOT_DIR))

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WebRPA-Desktop")


def load_env_file():
    """从 .env 文件加载环境变量到字典"""
    env_vars = {}
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()
    return env_vars


# 自定义右键菜单和快捷键注入脚本
INJECT_JS = """
(function() {
    // 1. 监听 F5 和 Cmd+R 刷新
    window.addEventListener('keydown', function(e) {
        if (e.key === 'F5' || (e.metaKey && e.key === 'r') || (e.ctrlKey && e.key === 'r')) {
            location.reload();
            e.preventDefault();
        }
    });

    // 2. 创建自定义右键菜单样式
    const style = document.createElement('style');
    style.innerHTML = `
        #custom-context-menu {
            position: fixed;
            display: none;
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 5px 0;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5);
            z-index: 10000;
            min-width: 150px;
            font-family: sans-serif;
            font-size: 13px;
        }
        .menu-item {
            padding: 8px 15px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .menu-item:hover { background: #334155; color: #60a5fa; }
        .menu-sep { height: 1px; background: #334155; margin: 5px 0; }
    `;
    document.head.appendChild(style);

    // 3. 创建菜单 DOM
    const menu = document.createElement('div');
    menu.id = 'custom-context-menu';
    menu.innerHTML = `
        <div class="menu-item" onclick="location.reload()">刷新页面 (F5)</div>
        <div class="menu-sep"></div>
        <div class="menu-item" onclick="window.history.back()">后退</div>
        <div class="menu-item" onclick="window.history.forward()">前进</div>
        <div class="menu-sep"></div>
        <div class="menu-item" onclick="window.location.href='/web'">返回工作站首页</div>
    `;
    document.body.appendChild(menu);

    // 4. 监听右键事件
    window.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        menu.style.left = e.pageX + 'px';
        menu.style.top = e.pageY + 'px';
        menu.style.display = 'block';
    });

    // 5. 点击其他地方隐藏菜单
    window.addEventListener('click', function() {
        menu.style.display = 'none';
    });
})();
"""

LAUNCHER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary: #3b82f6;
            --bg: #0f172a;
            --card: #1e293b;
            --text: #f8fafc;
            --border: #334155;
            --accent: linear-gradient(135deg, #60a5fa 0%, #a855f7 100%);
        }
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
            background-color: var(--bg);
            color: var(--text);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            overflow: hidden;
        }
        .container {
            background: var(--card);
            padding: 2.5rem;
            border-radius: 1.5rem;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
            width: 540px;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.05);
        }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }

        h1 { margin: 0 0 0.5rem 0; font-size: 1.8rem; font-weight: 800; background: var(--accent); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; }
        .subtitle { color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; text-align: center; }

        .section-title {
            font-size: 0.75rem;
            font-weight: 700;
            color: #60a5fa;
            margin: 1.5rem 0 1rem 0;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-title::after { content: ""; flex: 1; height: 1px; background: rgba(51, 65, 85, 0.5); }

        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .form-group { text-align: left; margin-bottom: 1rem; }
        .full-width { grid-column: span 2; }

        label { display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.4rem; font-weight: 500; }
        select, input {
            width: 100%;
            background: #0f172a;
            border: 1px solid var(--border);
            color: white;
            padding: 0.7rem 0.8rem;
            border-radius: 0.6rem;
            outline: none;
            font-size: 0.85rem;
            transition: border-color 0.2s;
        }
        select:focus, input:focus { border-color: var(--primary); }

        .checkbox-row { display: flex; gap: 1.5rem; margin: 1rem 0; padding: 0.8rem; background: rgba(15, 23, 42, 0.4); border-radius: 0.8rem; justify-content: center; }
        .checkbox-item { display: flex; align-items: center; gap: 0.6rem; cursor: pointer; }
        .checkbox-item input { width: 1rem; height: 1rem; cursor: pointer; }
        .checkbox-item span { font-size: 0.85rem; color: #cbd5e1; }

        button {
            width: 100%;
            background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
            color: white; border: none; padding: 1rem; border-radius: 0.8rem;
            font-size: 1rem; font-weight: 700; cursor: pointer; margin-top: 1rem;
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);
            transition: all 0.3s;
        }
        button:hover { transform: translateY(-2px); filter: brightness(1.1); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }

        .loader { display: none; margin-top: 1rem; color: #60a5fa; font-size: 0.8rem; align-items: center; justify-content: center; gap: 8px; }
        .spinner { width: 14px; height: 14px; border: 2px solid rgba(96, 165, 250, 0.2); border-top-color: #60a5fa; border-radius: 50%; animation: spin 0.8s linear infinite; }
    </style>
</head>
<body>
    <div class="container">
        <h1>WebRPA Workspace</h1>
        <div class="subtitle">桌面一体化控制中心 (支持右键刷新)</div>

        <div class="section-title">基础运行配置</div>
        <div class="form-grid">
            <div class="form-group">
                <label>运行模式</label>
                <select id="mode">
                    <option value="production">生产模式 (Stable)</option>
                    <option value="development">调试模式 (Reload)</option>
                </select>
            </div>
            <div class="form-group">
                <label>日志等级</label>
                <select id="log_level">
                    <option value="info">INFO (常规)</option>
                    <option value="debug">DEBUG (详细)</option>
                </select>
            </div>
        </div>

        <div class="checkbox-row">
            <label class="checkbox-item"><input type="checkbox" id="rpc" checked> <span>硬件 RPC</span></label>
            <label class="checkbox-item"><input type="checkbox" id="vlm" checked> <span>AI 视觉</span></label>
            <label class="checkbox-item"><input type="checkbox" id="strict" checked> <span>参数强校验</span></label>
        </div>

        <div class="section-title">AI 服务密钥 (ENV)</div>
        <div class="form-group">
            <label>LLM API KEY (DeepSeek/OpenAI)</label>
            <input type="password" id="env_llm_key" placeholder="sk-..." value="">
        </div>
        <div class="form-group">
            <label>VLM API KEY (UI-TARS)</label>
            <input type="password" id="env_vlm_key" placeholder="uitars-..." value="">
        </div>

        <div class="section-title">进阶系统参数</div>
        <div class="form-grid">
            <div class="form-group">
                <label>并发限制 (Tasks)</label>
                <input type="number" id="env_max_tasks" value="32">
            </div>
            <div class="form-group">
                <label>僵尸心跳阈值 (秒)</label>
                <input type="number" id="env_stale_secs" value="300">
            </div>
            <div class="form-group full-width">
                <label>Redis 连接串 (可选重写)</label>
                <input type="text" id="env_redis_url" placeholder="redis://127.0.0.1:6379/0">
            </div>
        </div>

        <button id="startBtn" onclick="startService()">立即启动工作站</button>

        <div id="loader" class="loader">
            <div class="spinner"></div>
            <span>正在校验环境并启动服务...</span>
        </div>
    </div>

    <script>
        window.addEventListener('pywebviewready', () => {
            pywebview.api.get_initial_env().then(env => {
                if (env.MYT_LLM_API_KEY) document.getElementById('env_llm_key').value = env.MYT_LLM_API_KEY;
                if (env.MYT_VLM_API_KEY) document.getElementById('env_vlm_key').value = env.MYT_VLM_API_KEY;
                if (env.MYT_MAX_CONCURRENT_TASKS) document.getElementById('env_max_tasks').value = env.MYT_MAX_CONCURRENT_TASKS;
                if (env.MYT_TASK_STALE_RUNNING_SECONDS) document.getElementById('env_stale_secs').value = env.MYT_TASK_STALE_RUNNING_SECONDS;
                if (env.REDIS_URL) document.getElementById('env_redis_url').value = env.REDIS_URL;
            });
        });

        function startService() {
            const config = {
                mode: document.getElementById('mode').value,
                log_level: document.getElementById('log_level').value,
                enable_rpc: document.getElementById('rpc').checked,
                enable_vlm: document.getElementById('vlm').checked,
                strict_plugin: document.getElementById('strict').checked,
                env_overrides: {
                    MYT_LLM_API_KEY: document.getElementById('env_llm_key').value,
                    MYT_VLM_API_KEY: document.getElementById('env_vlm_key').value,
                    MYT_MAX_CONCURRENT_TASKS: document.getElementById('env_max_tasks').value,
                    MYT_TASK_STALE_RUNNING_SECONDS: document.getElementById('env_stale_secs').value,
                    REDIS_URL: document.getElementById('env_redis_url').value
                }
            };

            document.getElementById('loader').style.display = 'flex';
            const btn = document.getElementById('startBtn');
            btn.disabled = true;
            btn.innerText = '启动中...';

            pywebview.api.start_service(config);
        }
    </script>
</body>
</html>
"""


class LauncherAPI:
    def __init__(self):
        self.window = None
        self.server_process = None

    def get_initial_env(self):
        return load_env_file()

    def _check_redis(self):
        try:
            subprocess.run(["redis-cli", "ping"], capture_output=True, timeout=1)
        except Exception:
            if sys.platform == "darwin":
                subprocess.run(["brew", "services", "start", "redis"], capture_output=True)

    def _run_server_process(self, config):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)
        env["MYT_LOAD_DOTENV"] = "1"
        env["MYT_API_PORT"] = str(PORT)
        env["MYT_TASK_QUEUE_BACKEND"] = "redis"

        env["MYT_ENABLE_RPC"] = "1" if config.get("enable_rpc") else "0"
        env["MYT_ENABLE_VLM"] = "1" if config.get("enable_vlm") else "0"
        env["MYT_STRICT_PLUGIN_UNKNOWN_INPUTS"] = "1" if config.get("strict_plugin") else "0"

        overrides = config.get("env_overrides", {})
        for key, val in overrides.items():
            if val and val.strip():
                env[key] = val.strip()

        self._check_redis()

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "api.server:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
        ]
        if config.get("mode") == "development":
            cmd.append("--reload")
        cmd.extend(["--log-level", config.get("log_level", "info")])

        self.server_process = subprocess.Popen(cmd, env=env, cwd=str(ROOT_DIR))

    def start_service(self, config):
        self._run_server_process(config)

        def _wait_and_redirect():
            for _ in range(40):
                time.sleep(0.5)
                try:
                    with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                        self.window.load_url(f"http://127.0.0.1:{PORT}/web")
                        # 核心优化：在页面加载后注入刷新逻辑
                        time.sleep(1)  # 等待页面初步渲染
                        self.window.evaluate_js(INJECT_JS)
                        return
                except OSError:
                    continue
            logger.error("Startup timeout.")

        threading.Thread(target=_wait_and_redirect, daemon=True).start()

    def cleanup(self):
        if self.server_process:
            self.server_process.terminate()


def main():
    import webview

    api = LauncherAPI()

    window = webview.create_window(
        title="WebRPA 工作站",
        html=LAUNCHER_HTML,
        js_api=api,
        width=1280,
        height=850,
        background_color="#0f172a",
    )
    api.window = window
    window.events.closed += api.cleanup

    # 初始界面也注入一下快捷键
    window.events.loaded += lambda: window.evaluate_js(INJECT_JS)

    # 关闭 debug=True，避免自动弹出开发者工具
    webview.start(debug=False)


if __name__ == "__main__":
    main()
