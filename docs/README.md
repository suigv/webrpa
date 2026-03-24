---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
stale_after_days: 14
verification_method:
  - repo audit
  - tools/check_docs_freshness.py
---

# WebRPA Docs

这个目录现在只保留**当前可验证**的文档，不再保留历史日志、规划文档、外部参考副本或示例堆积。

文档系统规则：

- `docs/` 只放当前契约和当前状态。
- 历史过程、路线图、未来计划不再作为仓库文档保留。
- 临时计划、施工进度、复盘草稿、迁移清单必须放在 `docs/` 之外。
- 如果任务先用临时计划推进，完成后应先把当前仍成立的事实写回正式文档，再删除或归档该临时计划。
- 当前文档必须带 freshness 元信息，并通过 `tools/check_docs_freshness.py` 校验。
- 如果某条信息不能被当前代码、当前配置或当前验证命令支撑，就不应该写进这里。

## 当前文档

- [STATUS.md](STATUS.md)：当前状态与最近一次验证结果。
- [HTTP_API.md](HTTP_API.md)：当前后端 API 分组与稳定入口。
- [PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)：当前插件目录、manifest、payload 边界。
- [CONFIGURATION.md](CONFIGURATION.md)：当前配置面与关键运行时开关。
- [FRONTEND.md](FRONTEND.md)：当前前端开发、部署和提交契约。
- [AI_ONBOARDING.md](AI_ONBOARDING.md)：新 AI 会话进入仓库时的最短阅读顺序。

## 使用顺序

1. 先读 [STATUS.md](STATUS.md)。
2. 按需要读 [HTTP_API.md](HTTP_API.md)、[PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)、[CONFIGURATION.md](CONFIGURATION.md)、[FRONTEND.md](FRONTEND.md)。
3. AI 进入仓库前读 [AI_ONBOARDING.md](AI_ONBOARDING.md)。

## 校验

在仓库根目录执行：

```bash
./.venv/bin/python tools/check_docs_freshness.py
```
