# 配置与环境变量参考 (Configuration)

WebRPA 支持通过环境变量进行深度配置。你可以将这些变量直接写在启动命令中，或放入根目录的 `.env` 文件（需配合 `MYT_LOAD_DOTENV=1` 使用）。

---

## 1. 基础服务配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_API_PORT` | `8001` | API 服务监听端口。 |
| `MYT_API_HOST` | `127.0.0.1` | API 服务绑定地址。 |
| `MYT_LOAD_DOTENV` | `0` | 是否加载根目录下的 `.env` 文件。可选值：`1`, `true`, `yes`。 |
| `CORS_ORIGINS` | `""` | 允许跨域的域名列表，用逗号分隔（如 `http://localhost:3000,https://app.com`）。 |

---

## 2. 任务执行与调度

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_TASK_QUEUE_BACKEND` | `redis` | 任务队列后端。可选值：`redis`, `memory`。 |
| `MYT_REDIS_URL` | `redis://127.0.0.1:6379/0` | 当后端为 `redis` 时的连接地址。 |
| `MYT_MAX_CONCURRENT_TASKS` | `32` | 允许同时运行的最大任务并发数。 |
| `MYT_TASK_STALE_RUNNING_SECONDS` | `300` | 僵尸任务判定阈值（秒）。超时未更新的任务将被强制恢复为 `pending`。 |

---

## 3. AI / LLM 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_LLM_API_BASE_URL` | `https://api.openai.com/v1` | LLM API 地址（支持 OpenAI 兼容代理）。 |
| `MYT_LLM_API_KEY` | `""` | LLM API Key（优先级高于 `MYT_OPENAI_API_KEY`）。 |
| `MYT_OPENAI_API_KEY` | `""` | 备用 LLM API Key。 |
| `MYT_LLM_MODEL` | `gpt-5.4` | 默认使用的 LLM 模型名称。 |
| `UITARS_API_KEY` | `token` | UI-TARS VLM 服务 API Key。 |

---

## 4. 插件与 RPC 控制

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` | `1` | 严格模式开关。为 `1` 时，拒绝插件 `manifest.yaml` 未定义的输入参数。 |
| `MYT_ENABLE_RPC` | `1` | 是否加载 `mytRpc` 底层库。测试纯 Web 环境时可设为 `0`。 |
| `MYT_REAL_HARDWARE` | `0` | (仅测试使用) 设置为 `1` 以在运行 `pytest` 时强制启用真实硬件 RPC 驱动。 |
| `MYT_ENABLE_VLM` | `0` | 是否启用视觉大模型支持。 |

---

## 5. 行为拟真引擎 (Humanized Engine)

该引擎通过 `HumanizedConfig` 控制所有交互动作（浏览器、原生 APP）的拟人化程度。

### 核心控制参数
*   **启用开关** (`enabled`): 是否开启全局拟人化。
*   **坐标偏移** (`click_offset`): 针对点击动作注入的随机像素偏差。
*   **打字节奏** (`typing_delay`): 逐字输入时的随机间隔及单词间停顿。
*   **物理模拟**: 包含点击前的心理停顿、按压时长模拟等。

> **提示**：目前已实现“一套配置，全端生效”。你在前端控制台修改的参数将同时影响 Chrome 浏览器和 Native 设备的操作。

---

## 6. UI 配置与绑定

### 6.1 默认 App 配置
WebRPA 的 UI 选择器与 Scheme 配置存放在 `config/apps/`，默认读取 `config/apps/default.yaml`。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_DEFAULT_APP` | `default` | 当无法从 `params.app / payload.app / payload.package` 推断 App 时使用的默认配置名。 |

### 6.2 UI 状态绑定（可选）
AI/GPT 路径会从 `config/bindings/*.json` 动态加载 UI 状态绑定数据（按 `app_package` 匹配）。  
缺少绑定不会报错，系统会进入 **binding-free** 观察模式。

---

## 7. 路径与资源重定向

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_NEW_ROOT` | (自动识别) | 强制指定项目根目录路径。 |
| `MYT_USER_DATA_DIR` | `/tmp/webrpa_browser_profiles` | 浏览器 Profile 的持久化根目录。 |
| `MYT_RPC_LIB_PATH` | (自动识别) | 强制指定 `libmytrpc` 等原生库的存放路径。 |
| `MYT_CREDENTIAL_ALLOWLIST` | `/etc/myt` | 凭据加载器允许访问的物理目录。 |

---

## 8. 典型配置场景

### 场景 A：单机纯内存轻量运行
适合开发调试或纯 Web 自动化。
```bash
MYT_TASK_QUEUE_BACKEND=memory MYT_ENABLE_RPC=0 uv run python api/server.py
```

### 场景 B：生产环境高可用部署
配合 Redis 实现任务持久化。
```bash
MYT_LOAD_DOTENV=1 MYT_TASK_QUEUE_BACKEND=redis uv run uvicorn api.server:app --port 8001
```
