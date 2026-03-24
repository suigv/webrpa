---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
stale_after_days: 14
verification_method:
  - docs structure audit
  - manual repo audit
---

# AI Onboarding

新 AI 会话进入仓库时，只读这组当前文档：

1. [README.md](README.md)
2. [STATUS.md](STATUS.md)
3. [HTTP_API.md](HTTP_API.md)
4. [PLUGIN_CONTRACT.md](PLUGIN_CONTRACT.md)
5. [CONFIGURATION.md](CONFIGURATION.md)
6. [FRONTEND.md](FRONTEND.md)

## 规则

- `docs/` 里的文档都应被视为当前契约。
- 仓库里不再保留路线图、历史日志、未来规划文档；不要自行脑补这些材料仍然存在。
- 如果代码改动影响契约，先更新当前文档，再结束工作。
- 不要把未验证能力写成已完成能力。

## 新会话首句建议

```text
请先阅读 docs/README.md 和 docs/STATUS.md，再按需阅读 HTTP_API、PLUGIN_CONTRACT、CONFIGURATION、FRONTEND 后开始修改。
```
