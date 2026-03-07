# Current Main Status

更新时间：2026-03-07

## 已完成

- atomicity remediation 已合入 `main`
- selector 生命周期清理已补齐，解释器退出时会释放 selector-backed RPC 资源
- shared JSON store 已具备原子写入、同进程锁与跨进程文件锁保护
- `ui_actions` / `sdk_actions` 已做热点收敛，避免继续无边界膨胀
- 原子化相关中文说明文档、参考审查文档、README 入口均已同步
- `progress-sync` CI 已修复为确定性输出，不再因时间戳造成假失败

## 部分完成

- `重复实现`：shared store 与 selector 生命周期已收敛，但共享 RPC helper 仍未统一抽取
- `边界混乱`：`ui_actions` / `sdk_actions` 已处理主要热点，但 `core/task_control.py` 仍是后续重点

## 当前分支不适用

- `x_mobile_login` 的超长 fallback workflow 压缩
- login composite actions 批量补齐

原因：当前 `main` 上的 `plugins/x_mobile_login/script.yaml` 已不是最初审查时的超长 workflow 形态。

## 下一步优先级

1. 提取共享 RPC helper，降低 `ui_actions` / `state_actions` 的重复接入逻辑
2. 继续收敛 `core/task_control.py` 的职责边界
3. 如果登录/引导类 workflow 再次膨胀，再补 composite action 而不是继续复制 YAML

## 参考文档

- `功能原子化问题分类说明.md`
- `功能原子化修复结果.md`
- `docs/reference/atomicity_architecture_review.md`
