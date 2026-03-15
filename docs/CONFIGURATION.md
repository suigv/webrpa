# 配置与环境变量参考 (Configuration)

WebRPA 采用 `config/system.yaml` 作为**全局系统配置**的唯一来源（非敏感信息）。你需要在该文件中配置基础服务连接（Redis, LLM, VLM 等）、依赖路径和开关。
对于敏感数据（如 API Key）或临时覆盖选项，仍使用环境变量配置。你可以将这些变量直接写在启动命令中，或放入根目录的 `.env` 文件（需配合 `MYT_LOAD_DOTENV=1` 使用）。

---

## 1. 基础服务配置 (Environment Variables)

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_API_PORT` | `8001` | API 服务监听端口。 |
| `MYT_API_HOST` | `127.0.0.1` | API 服务绑定地址。 |
| `MYT_LOAD_DOTENV` | `0` | 是否加载根目录下的 `.env` 文件。可选值：`1`, `true`, `yes`。 |
| `CORS_ORIGINS` | `""` | 允许跨域的域名列表，用逗号分隔（如 `http://localhost:3000,https://app.com`）。 |

---

## 2. 核心系统配置 (config/system.yaml)

`config/system.yaml` 是核心服务的单点配置，包括：
- **features**: 开关项（`enable_rpc`, `enable_vlm`）
- **services**: 包含 `redis_url`, `llm` (base_url, model), `vlm` (base_url, model)
- **paths**: `browser_profiles_dir`, `ai_work_dir`
- **credentials**: `allowlist` 凭据文件的解析根路径列表，使用冒号分隔目录

*(注：系统包含内置默认值。如果 `system.yaml` 文件缺失，服务仍可使用内部默认值正常启动。但生产建议显示创建与维护此文件)*

---

## 3. 安全与敏感配置 (Secrets / API Keys)

为了安全起见，所有密钥（Secret）不得写入 `system.yaml` 等持久化文件，必须通过环境变量注入：

| 环境变量 | 说明 |
|---|---|
| `MYT_LLM_API_KEY_{PROVIDER}` | 特定服务商的 API Key（如 `MYT_LLM_API_KEY_DEEPSEEK`）。优先级最高。 |
| `MYT_LLM_API_KEY` | 全局兜底 LLM API Key。 |
| `MYT_VLM_API_KEY_{PROVIDER}` | 特定视觉服务商的 API Key（如 `MYT_VLM_API_KEY_VLM`）。优先级最高。 |
| `MYT_VLM_API_KEY` | 全局 VLM 兜底密钥。 |

---

## 4. 任务执行与调度覆盖项

下列环境变量用于调整底层队列和任务生命周期：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_TASK_QUEUE_BACKEND` | `redis` | 任务队列后端。可选值：`redis`, `memory`。 |
| `MYT_MAX_CONCURRENT_TASKS` | `32` | 允许同时运行的最大任务并发数。 |
| `MYT_TASK_STALE_RUNNING_SECONDS` | `300` | 僵尸任务判定阈值（秒）。超时未更新的任务将被强制恢复为 `pending`。 |

---

## 5. 插件与测试覆盖开关

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MYT_STRICT_PLUGIN_UNKNOWN_INPUTS` | `1` | 严格模式开关。为 `1` 时，拒绝插件 `manifest.yaml` 未定义的输入参数。 |
| `MYT_ENABLE_RPC` | (由yaml决定) | 环境变量覆盖是否加载 `mytRpc` 底层库。设为 `0` 可绕过硬件依赖进行纯 Web 开发。 |
| `MYT_REAL_HARDWARE` | `0` | (仅测试使用) 设置为 `1` 以在运行 `pytest` 时强制启用真实硬件 RPC 驱动。 |
| `MYT_ENABLE_VLM` | (由yaml决定) | 环境变量覆盖是否启用视觉大模型支持。 |
| `MYT_DATA_SUBDIR` | `""` | 将所有运行时数据写入 `config/data/<subdir>/`（必须是安全的相对路径；用于测试隔离或多实例本地运行）。 |

> 说明：设备相关调试接口（如 `GET /api/devices/{device_id}/{cloud_id}/screenshot`）会从 `config/devices.json` 解析设备 IP，并使用端口公式推导 `rpa_port`，不会接受请求参数直接指定 IP/Port。

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
AI/GPT 路径会从 `config/apps/*.yaml` 动态加载 UI 状态绑定数据（按 `package_name` 字段匹配）。
`xml_filter` 和 `states` 字段与选择器配置统一存放在同一文件中。
缺少绑定不会报错，系统会进入 **binding-free** 观察模式。

---

## 7. 账号运营角色 (ai_type)

`ai_type` 是账号级别的**运营角色标识**，用于选取文案、关键词策略和候选人评分权重。与 LLM provider 无关。

| 值 | 含义 |
|---|---|
| `volc` | 主力运营角色，使用积极主动的互动风格 |
| `part_time` | 兼职/辅助角色，使用更简短克制的互动风格 |
| `default` | 兜底默认风格（未匹配时的回退） |

设备默认值通过 `config/devices.json` 中每台设备的 `default_ai` 字段指定，全局兜底为 `default`。

### 配置文件

| 文件 | 作用 |
|---|---|
| `config/strategies/interaction_texts.yaml` | 文案池（DM 回复、引用推文、搜索词等），按 `section → ai_type → []` 三级结构 |
| `config/strategies/nurture_keywords.yaml` | 关键词策略及候选人评分权重，按 `strategies → ai_type` 结构 |
| `config/strategies/login_stage_patterns.yaml` | 登录阶段识别（captcha/two_factor/password/account/home 等）的默认识别规则；也可在 action 参数中用 `stage_patterns/stage_order` 覆盖。 |
| `config/strategies/state_action_defaults.yaml` | 状态类 action（如 follow/unread/DM 分隔符）的默认 UI 文本/标记；也可通过 action 参数覆盖。 |

### 新增运营角色

只需在两个 yaml 文件中各增加一个同名 key，框架代码**零改动**：

```yaml
# interaction_texts.yaml
search_query:
  my_new_role:
    - "#mytag"

# nurture_keywords.yaml
strategies:
  my_new_role:
    candidate_scoring:
      has_media_bonus: 5
      keyword_bonuses:
        - {text: "关键词", score: 8}
    weights: {core: 5}
    keywords:
      core: ["示例关键词"]
    blacklist: []
```

---

## 9. 数据持久化 (Storage & Data)

| 内容 | 路径 | 说明 |
|---|---|---|
| 任务数据库 | `config/data/tasks.db` | 核心任务与事件流存储 (SQLite)。 |
| 账号池数据库 | `config/data/accounts.json.db` | 账号池存储 (SQLite)，支持并发抽号。 |
| 浏览器配置 | `config/browser_profiles/` | Chrome 用户配置文件缓存。 |
| AI 过程轨迹 | `config/data/traces/` | Agent Executor 的中间决策过程记录。 |

> 注意：`config/data/` 属于运行产物目录，默认不应纳入 git 版本控制（仓库会忽略该目录，保留 `.gitkeep` 占位）。

---

## 典型配置场景

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

---

## 附：蒸馏门槛 (Distillation Threshold)

每个插件可在 `plugins/<plugin>/manifest.yaml` 中声明 `distill_threshold`（默认 `3`），用于决定 `POST /api/tasks/distill/{plugin_name}` 的触发门槛。
