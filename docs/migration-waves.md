# 迁移波次（Task 4）

目标：控制风险与交付节奏，避免“全量一波次”导致回归不可控。

## Wave A（低风险高收益）

1. `task_reboot_device`（device_reboot 插件）
2. `task_soft_reset`（device_soft_reset 插件）
3. `task_login`（x_mobile_login 插件）

理由：设备控制与登录链路是后续任务的基础能力。

## Wave B（数据与资料链路）

1. `task_scrape_blogger`（blogger_scrape 插件）
2. `task_clone_profile`（profile_clone 插件）
3. `任务目录控制面`（task catalog + payload contract）

理由：先打通“采集→仿冒→可调用目录”。

## Wave C1（互动链路第一批）

1. `task_follow_followers`
2. `task_home_interaction`
3. `task_quote_intercept`

## Wave C2（互动链路第二批）

1. `task_reply_dm`
2. `task_nurture`
3. `端到端回归与切换评估`

## 依赖闭合

- Wave A 完成后，提供 app 生命周期、登录状态与设备可用性基础。
- Wave B 依赖 Wave A（登录态 + 基础动作），并为 Wave C 提供博主池/资料链路。
- Wave C1/C2 依赖 Wave B 的数据与资料能力，避免任务间隐式耦合。
