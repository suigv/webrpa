---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
stale_after_days: 14
verification_method:
  - ./.venv/bin/python tools/check_no_legacy_imports.py
  - ./.venv/bin/python -m pytest tests -q
  - ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
  - curl http://127.0.0.1:8001/health
  - MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
  - ./.venv/bin/python tools/check_docs_freshness.py
---

# Current Status

本文件只记录**当前成立**且已经被代码或验证命令支撑的状态。

## 当前范围

当前仓库确认存在并对外暴露的能力：

- FastAPI 服务入口：`api.server:app`
- 健康检查与控制面 API：`/health`、`/api/*`
- 设备与云机接口：`/api/devices/*`
- 托管任务系统：`/api/tasks/*`
- AI 对话接口：`/api/ai_dialog/*`
- 插件执行引擎与动作目录：`plugins/`、`/api/engine/schema`、`/api/engine/skills`
- 前端控制台工程：`web/`

## 最近一次验证

2026-03-24 这组命令为当前文档系统的验证基线：

```bash
./.venv/bin/python tools/check_no_legacy_imports.py
./.venv/bin/python -m pytest tests -q
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
./.venv/bin/python tools/check_docs_freshness.py
```

## 当前已确认的仓库事实

- `docs/` 现在只保留当前文档，不再保留规划、历史、参考副本和示例目录。
- 后端仍保留 `/web` 入口，但前端是独立的 Vite 工程，部署方式见 [FRONTEND.md](FRONTEND.md)。
- 当前仓库存在 10 个插件 manifest：
  - `device_reboot`
  - `one_click_new_device`
  - `x_clone_profile`
  - `x_follow_followers`
  - `x_home_interaction`
  - `x_login`
  - `x_nurture`
  - `x_quote_intercept`
  - `x_reply_dm`
  - `x_scrape_blogger`
- 当前动作目录支持按 `tag` 过滤，并提供 `/api/engine/skills` 作为 AI-facing skill 集合。

## 当前明确不声明的内容

- 不声明任何未来路线图、阶段名、里程碑计划。
- 不声明浏览器 hands-on QA 已完整完成。
- 不声明 WebRTC 接管、自动 promotion pipeline 等未在当前代码和当前验证里锁定的能力。
