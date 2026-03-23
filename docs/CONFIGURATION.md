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
| `MYT_CORS_ALLOW_ORIGINS` | `*` | 允许跨域的 Origin 列表，用逗号分隔；`*` 表示允许所有。 |
| `MYT_CORS_ALLOW_CREDENTIALS` | `0` | 是否允许携带 credentials（cookie 等）。本项目推荐使用 Bearer token，不依赖 cookie。 |
| `MYT_FRONTEND_URL` | `""` | 控制台入口 URL；设置后 `/web` 会 307 重定向到该地址（通常是 Vite 或 Nginx 托管的前端）。 |
| `MYT_AUTH_MODE` | `disabled` | 鉴权模式；设为 `jwt` 后 `/api/*` 强制要求 `Authorization: Bearer <jwt>`。 |
| `MYT_JWT_SECRET` | `""` | JWT HMAC secret（HS256）。建议至少 32 bytes。 |
| `MYT_AUTH_PROTECT_OPENAPI` | `0` | 是否保护 `/openapi.json`（设为 `1` 时需要 Bearer token 才能拉取 OpenAPI schema）。 |

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
| `MYT_TASK_CANCEL_GRACE_SECONDS` | `10` | 子进程任务收到取消信号后的宽限期；超时后父进程会发送 `terminate()`。 |
| `MYT_TASK_FORCE_KILL_SECONDS` | `30` | 子进程任务在 `terminate()` 后仍未退出时的强杀阈值。 |
| `MYT_QUEUE_AGING_INTERVAL` | `120` | 内存队列优先级老化周期（秒）；仅 `memory` 队列生效。 |
| `MYT_QUEUE_AGING_BOOST` | `10` | 每个老化周期提升的优先级点数；仅 `memory` 队列生效。 |
| `MYT_DEVICE_SNAPSHOT_TTL_SECONDS` | `2` | 设备快照缓存 TTL；过期后会重建快照，避免 UI 长时间显示旧 probe 结果。 |

---

### 4.1 设备可用性提前熔断

- `CloudProbeService` 会持续把云机探测结果写入 `DeviceManager`。
- 活跃任务在执行 target 时会消费对应 probe 状态；当连续探测失败达到 unavailable 阈值后，任务会提前返回 `failed_circuit_breaker`，错误码为 `target_unavailable`。
- 该机制不会把 `mark_cloud_released()` 当成成功 probe，因此释放占用不会把真实离线设备错误刷回 `available`。
- stale probe 默认不会触发熔断；只有明确进入 `unavailable` 状态才会提前终止。

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

### 5.1 设备发现优先级

- 运行时优先使用局域网自动发现结果；只有在 discovery 没有命中设备时，才回退到 `host_ip` / `device_ips`。
- `host_ip` 仍然保留，用于 discovery 失败时的兜底地址和单机兼容模式。
- `discovery_subnet` 仅作为兼容覆盖项保留；当前默认行为会优先从本机有效 IPv4 自动推导 `/24` 网段，前端/客户侧不应再要求手工理解和输入网段。
- `total_devices` 只有在 discovery 命中设备时才会被发现结果覆盖；静态模式下仍以配置值为准，避免因为 `device_ips` 只显式配置了部分编号而压缩拓扑。

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

### 6.2 UI 状态配置（可选）
AI/Agent 路径会从 `config/apps/*.yaml` 动态加载 UI 状态配置（按 `package_name` 字段匹配）。
`xml_filter` 和 `states` 字段与选择器配置统一存放在同一文件中。
缺少状态配置不会报错，系统会进入 **state-profile-free** 观察模式。

---

## 7. 账号运营角色 (ai_type)

`ai_type` 是插件 payload 内的**运营角色标识**，用于选取文案、关键词策略和候选人评分权重。与 LLM provider 无关。

| 值 | 含义 |
|---|---|
| `volc` | 主力运营角色，使用积极主动的互动风格 |
| `part_time` | 兼职/辅助角色，使用更简短克制的互动风格 |
| `default` | 兜底默认风格（未匹配时的回退） |

当前没有系统级或设备级 `default_ai` 公共配置。
如需指定运营角色，应由调用方在任务 `payload.ai_type` 中显式传入；未传入时相关动作自行回退到 `default`。

### 配置文件

| 文件 | 作用 |
|---|---|
| `config/strategies/interaction_texts.yaml` | 文案池（DM 回复、引用推文、搜索词等），按 `section → ai_type → []` 三级结构 |
| `config/strategies/nurture_keywords.yaml` | 关键词策略及候选人评分权重，按 `strategies → ai_type` 结构 |
| `config/strategies/login_stage_patterns.yaml` | 登录阶段识别（captcha/two_factor/password/account/home 等）的全局默认规则；仅作为 framework fallback，不承载单 App 在线学习结果。 |
| `config/strategies/state_action_defaults.yaml` | 状态类 action（如 follow/unread/DM 分隔符）的默认 UI 文本/标记；也可通过 action 参数覆盖。 |

应用级感知记忆位于 `config/apps/<app>.yaml` 的 `stage_patterns` 字段。在线学习只回写该字段，不会自动污染 `config/strategies/login_stage_patterns.yaml`。

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

## 8. 多应用感知与包名注入 (App-Awareness)

WebRPA 支持在一个设备上切换操作不同的应用程序。通过 `config/apps/` 目录下的配置文件，系统可以自动感知上下文并补全包名。

### 应用配置文件 (`config/apps/<app_id>.yaml`)

| 字段 | 说明 |
|---|---|
| `package_name` | 应用程序的 Android 包名。 |
| `name` | (可选) 应用的友好显示名称。 |
| `states` | 定义应用特有的 UI 状态。 |
| `selectors` | 定义常用的 UI 元素选择器。 |

### 工作逻辑

1. **导入环节**：在导入账号时，用户需指定该账号所属的 `app_id` (如 `x`, `tiktok`)。
2. **下发环节**：提交任务时，通过 `app_id` 选择器指定任务的上下文环境。
3. **注入环节**：`Runner` 在执行插件前，若发现 `payload` 中缺少 `package` 字段，会自动根据 `app_id` 从对应的 YAML 配置中提取 `package_name` 并注入。

这样设计实现了 **“按需开启”**：
- **基础插件** (如“软件复位”)：只需声明需要 `package` 参数，系统将自动补全，用户无需手动输入。
- **业务插件**：依然可以保留 `required: true` 强制要求用户输入自定义参数。

---

## 9. 数据持久化 (Storage & Data)

| 内容 | 路径 | 说明 |
|---|---|---|
| 任务数据库 | `config/data/tasks.db` | 核心任务与事件流存储 (SQLite)。 |
| 账号池数据库 | `config/data/accounts.json.db` | 账号池存储 (SQLite)，支持并发抽号。 |
| 浏览器配置 | `paths.browser_profiles_dir`（默认 `/tmp/webrpa_browser_profiles/`） | Chrome 用户配置文件缓存。 |
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

每个插件可在 `plugins/<plugin>/manifest.yaml` 中声明：

- `distillable`：是否允许进入蒸馏链路，默认 `true`
- `distill_threshold`：达到多少次成功后才允许蒸馏，默认 `3`

推荐规则：

- 业务 UI 流程插件：保留 `distillable: true`
- 设备初始化、环境编排、随机化、运维类插件：设置 `distillable: false`

例如 `one_click_new_device` 这类任务，目标是“重置并随机化一台设备环境”，不是“沉淀一条可复刻的 AI 操作路径”，因此应明确标记为不可蒸馏。
