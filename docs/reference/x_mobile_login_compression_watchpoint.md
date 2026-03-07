# `x_mobile_login` compression watchpoint

更新时间：2026-03-08

## 结论

当前分支上的 `plugins/x_mobile_login/script.yaml:1` 仍然是一个需要继续观察的长 workflow，但证据还不支持把它重新升级为“现在必须做 composite-action 压缩”的改造项。

- 当前结论：**保留 watchpoint，不做 refactor 结论**。
- 依据不是“脚本很短”，而是“当前分支的复杂度形态，没有完全重现旧审查文档描述的那种失控 fallback 膨胀”。
- 旧文档里把它列成明显异常值，这个判断需要保留上下文，因为旧文档描述的是“应优先拆”的风险视角，不是当前主分支的强制执行项，见 `docs/reference/atomicity_architecture_review.md:17` 与 `docs/reference/atomicity_architecture_review.md:29`。

## 当前工作流形态

`plugins/x_mobile_login/script.yaml:1` 现在仍是单文件长脚本，总长度约 705 行，见 `docs/reference/atomicity_architecture_review.md:36`。但它的结构是可辨认的几段，而不是无边界扩散：

- 输入与状态 hint 契约集中在 `plugins/x_mobile_login/script.yaml:4`，对应 manifest 输入声明在 `plugins/x_mobile_login/manifest.yaml:12`。
- selector 预加载集中在 `plugins/x_mobile_login/script.yaml:49`，当前是 8 个 `core.load_ui_selector` 步骤。
- runtime 接线与入口状态识别集中在 `plugins/x_mobile_login/script.yaml:105` 和 `plugins/x_mobile_login/script.yaml:142`。
- 账号输入主路径集中在 `plugins/x_mobile_login/script.yaml:188`，密码输入主路径集中在 `plugins/x_mobile_login/script.yaml:301`。
- 2FA 分支集中在 `plugins/x_mobile_login/script.yaml:456`，成功与失败 stop 契约集中在 `plugins/x_mobile_login/script.yaml:446` 和 `plugins/x_mobile_login/script.yaml:652`。

当前脚本里确实还能看到重复模式，但它们主要落在少数几个登录阶段：

- 8 个 selector preload。
- 12 个 `ui.selector_click_one`。
- 6 个 `mytos.tap` fallback。
- 4 个 `device.exec` 输入 fallback。
- 10 个显式 `*fallback` 标签，集中在账号、密码、登录提交、2FA 输入这几类路径。

这说明它还是长脚本，也说明它还没完全摆脱 fallback 编排，但重复密度还没有新证据证明它已经再次恶化到必须立刻抽 composite action。

## 与旧文档的对照

旧审查资料确实把 `x_mobile_login` 当作典型异常值处理：

- `docs/reference/atomicity_architecture_review.md:29` 直接写它是“明显异常值”。
- `docs/reference/atomicity_architecture_review.md:69` 认为它包含大量重复 selector 加载、点击回退、输入回退、状态分支。
- `docs/reference/atomicity_architecture_review.md:107` 把它列为当前最不合理设计点之一。
- `docs/reference/atomicity_architecture_review.md:123` 和 `docs/reference/atomicity_architecture_review.md:148` 都建议补 2 到 3 个复合动作来压缩脚本。

但后续主分支状态文档已经明确把这件事降级为“当前分支不适用”：

- `docs/current_main_status.md:22` 把“`x_mobile_login` 的超长 fallback workflow 压缩”列进“当前分支不适用”。
- `docs/current_main_status.md:25` 说明原因是当前 `main` 上的脚本已经不是最初审查时的超长 workflow 形态。
- `功能原子化问题分类说明.md:11` 和 `功能原子化问题分类说明.md:138` 同样说明当前分支不再是旧审查里的同一形态。
- `功能原子化修复结果.md:78` 和 `功能原子化修复结果.md:84` 也把 login fallback composite actions 与 workflow 压缩列为当前 worktree 不适用。

因此，这里的正确 reconciliation 不是推翻旧文档，也不是忽略旧文档，而是把旧文档理解为“风险识别来源”，把较新的状态文档理解为“当前分支裁决”。

## 现有测试与证据边界

当前相邻运行时测试覆盖的是状态契约，不是 workflow 压缩收益：

- `tests/test_x_mobile_login_runtime.py:4` 覆盖 success hint。
- `tests/test_x_mobile_login_runtime.py:10` 覆盖 bad credentials。
- `tests/test_x_mobile_login_runtime.py:17` 覆盖 2FA failed。
- `tests/test_x_mobile_login_runtime.py:24` 覆盖 captcha。
- `tests/test_x_mobile_login_runtime.py:31` 覆盖 `MYT_ENABLE_RPC=0` 下不会误报成功。

这组测试支持的结论是：当前 plugin 仍承担明确的状态 stop 契约。它们**不**构成“现在已经因为重复模式而难以维护”的新证据。

## 重新开启 compression work 的标准

只有出现下面任一条，再重新开启 composite-action 压缩 work，才算 repo-backed：

1. `plugins/x_mobile_login/script.yaml:1` 再次出现同一 fallback 组合新增 3 次或以上，尤其是“selector 点击，再坐标 tap 回退”或“UI 输入，再 shell 输入回退”被复制到新的登录阶段，而不是只停留在现有账号、密码、2FA 三组路径。
2. `plugins/x_mobile_login/script.yaml:49` 这一段 selector preload 明显继续膨胀，当前 8 个 `load_*_selector` 增长到 12 个以上，或开始按语言、页面变体重复预加载同类 selector。
3. 脚本长度在当前约 705 行的基础上继续增长超过约 25%，也就是接近或超过 850 行，同时增长主要来自 fallback 编排，而不是单纯新增一个独立状态出口。
4. 相邻测试需要为了同一登录意图补越来越多细碎状态契约，导致 `tests/test_x_mobile_login_runtime.py:4` 这类契约测试不再足以表达主路径，说明 workflow 分支已经开始挤压可验证性。
5. 新文档或代码再次出现与 `docs/reference/atomicity_architecture_review.md:141` 一致的信号，也就是同一种 fallback 组合在 workflow 内重复 3 次以上，已经满足项目级 composite action 触发线。

## 当前 watchpoint 结论

- `x_mobile_login` 仍然值得盯住，因为它依旧是仓库里较长的 plugin workflow，见 `docs/reference/atomicity_architecture_review.md:36`。
- 但就当前分支证据看，它更像“长但仍可解释的登录状态契约脚本”，不是“已经再次失控、必须马上压缩”的 blocker。
- 所以当前分支的明确结论是：**继续保留 watchpoint，暂不重开 composite-action compression work**。

## 相关文件

- 插件脚本：`plugins/x_mobile_login/script.yaml:1`
- 插件 manifest：`plugins/x_mobile_login/manifest.yaml:1`
- 相邻运行时测试：`tests/test_x_mobile_login_runtime.py:1`
- 当前主分支状态：`docs/current_main_status.md:20`
- 中文分类说明：`功能原子化问题分类说明.md:104`
- 中文修复结果：`功能原子化修复结果.md:72`
- 旧架构审查：`docs/reference/atomicity_architecture_review.md:24`
