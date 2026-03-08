# `x_mobile_login` compression watchpoint

更新时间：2026-03-08

## 结论

当前主分支上的 `plugins/x_mobile_login/script.yaml:1` 已经完成一轮定向 fallback-chain 缩减，但它仍然是一个需要继续观察的长 workflow。

- 当前结论：**定向压缩已落地，继续保留 watchpoint，不把它表述成整插件重写。**
- 已落地的变化是复用现有 composite action，去掉登录主路径中的重复 selector→tap 和 focus→input→shell fallback 编排。
- 旧文档里把它列成明显异常值，这个判断仍有参考价值，但要和当前已落地的最小修复区分开。

## 当前工作流形态

`plugins/x_mobile_login/script.yaml:1` 现在仍是单文件长脚本，总长度约 567 行。但它的结构是可辨认的几段，而且关键登录路径已经不再保留之前那种重复 fallback 链：

- 输入与状态 hint 契约集中在 `plugins/x_mobile_login/script.yaml:4`，对应 manifest 输入声明在 `plugins/x_mobile_login/manifest.yaml:12`。
- selector 预加载集中在 `plugins/x_mobile_login/script.yaml:49`，当前是 8 个 `core.load_ui_selector` 步骤。
- runtime 接线与入口状态识别集中在 `plugins/x_mobile_login/script.yaml:105` 和 `plugins/x_mobile_login/script.yaml:142`。
- 账号输入主路径集中在 `plugins/x_mobile_login/script.yaml:188`，密码输入主路径集中在 `plugins/x_mobile_login/script.yaml:301`。
- 2FA 分支集中在脚本后半段，成功与失败 stop 契约集中在最后几组 `stop` 节点。

当前脚本里仍有重复模式，但热点已经缩到少数几个登录阶段：

- 8 个 selector preload。
- 仍保留若干 `ui.selector_click_one` 单点点击步骤。
- 输入主路径已统一复用 `ui.focus_and_input_with_shell_fallback`。
- 登录入口行和登录提交路径已复用 `ui.click_selector_or_tap`。

这说明它还是长脚本，也说明它还没完全摆脱 fallback 编排，但 task 8 对应的最小安全压缩已经落地，不该继续写成“当前分支不适用”。

## 与旧文档的对照

旧审查资料确实把 `x_mobile_login` 当作典型异常值处理：

- `docs/reference/atomicity_architecture_review.md:29` 直接写它是“明显异常值”。
- `docs/reference/atomicity_architecture_review.md:69` 认为它包含大量重复 selector 加载、点击回退、输入回退、状态分支。
- `docs/reference/atomicity_architecture_review.md:107` 把它列为当前最不合理设计点之一。
- `docs/reference/atomicity_architecture_review.md:123` 和 `docs/reference/atomicity_architecture_review.md:148` 都建议补 2 到 3 个复合动作来压缩脚本。

但当前代码已经比这些旧状态文档再往前走了一步：

- `script.yaml` 已复用 `ui.click_selector_or_tap` 处理登录入口行与登录提交路径的 selector 点击回退。
- `script.yaml` 已复用 `ui.focus_and_input_with_shell_fallback` 处理账号、密码、2FA 输入路径。
- 因此，旧文档里“当前分支不适用”的口径需要更新成“已完成定向压缩，继续保留 watchpoint”。

因此，这里的正确 reconciliation 不是推翻旧审查，也不是夸大成 repo-wide rewrite，而是明确说明：旧文档提供风险识别来源，当前主分支则已经对最重复的 fallback 链做了最小安全收口。

## 现有测试与证据边界

当前相邻运行时测试覆盖的是状态契约，不是 workflow 压缩收益：

- `tests/test_x_mobile_login_runtime.py:4` 覆盖 success hint。
- `tests/test_x_mobile_login_runtime.py:10` 覆盖 bad credentials。
- `tests/test_x_mobile_login_runtime.py:17` 覆盖 2FA failed。
- `tests/test_x_mobile_login_runtime.py:24` 覆盖 captcha。
- `tests/test_x_mobile_login_runtime.py:31` 覆盖 `MYT_ENABLE_RPC=0` 下不会误报成功。

这组测试支持的结论是：当前 plugin 仍承担明确的状态 stop 契约，而压缩工作是在不改状态/分支标签语义的前提下完成的。

## 重新开启 compression work 的标准

只有出现下面任一条，再重新开启下一轮 compression work，才算 repo-backed：

1. `plugins/x_mobile_login/script.yaml:1` 再次出现同一 fallback 组合新增 3 次或以上，尤其是已经被 composite action 吸收的“selector 点击，再坐标 tap 回退”或“focus 后输入，再 shell 输入回退”又被展开写回 YAML。
2. `plugins/x_mobile_login/script.yaml:49` 这一段 selector preload 明显继续膨胀，当前 8 个 `load_*_selector` 增长到 12 个以上，或开始按语言、页面变体重复预加载同类 selector。
3. 脚本长度在当前约 567 行的基础上继续增长超过约 25%，也就是接近或超过 710 行，同时增长主要来自 fallback 编排，而不是单纯新增一个独立状态出口。
4. 相邻测试需要为了同一登录意图补越来越多细碎状态契约，导致 `tests/test_x_mobile_login_runtime.py:4` 这类契约测试不再足以表达主路径，说明 workflow 分支已经开始挤压可验证性。
5. 新文档或代码再次出现与 `docs/reference/atomicity_architecture_review.md:141` 一致的信号，也就是同一种 fallback 组合在 workflow 内重复 3 次以上，已经满足项目级 composite action 触发线。

## 当前 watchpoint 结论

- `x_mobile_login` 仍然值得盯住，因为它依旧是仓库里较长的 plugin workflow。
- 但就当前分支证据看，它更像“已经做过定向压缩、仍需继续观察的登录状态契约脚本”，不是“当前分支不适用”，也不是“必须立刻全面重写”的 blocker。
- 所以当前主分支的明确结论是：**定向 composite-action 压缩已完成，继续保留 watchpoint，暂不重开更大范围 compression work**。

## 相关文件

- 插件脚本：`plugins/x_mobile_login/script.yaml:1`
- 插件 manifest：`plugins/x_mobile_login/manifest.yaml:1`
- 相邻运行时测试：`tests/test_x_mobile_login_runtime.py:1`
- 当前主分支状态：`docs/current_main_status.md`
- 中文分类说明：`docs/reference/功能原子化问题分类说明.md`
- 中文修复结果：`docs/reference/功能原子化修复结果.md`
- 旧架构审查：`docs/reference/atomicity_architecture_review.md:24`
