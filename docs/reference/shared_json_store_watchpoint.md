# shared JSON store watchpoint

更新时间：2026-03-08

## 结论

**Verdict: watchpoint only**

当前仓库里的 shared JSON store 还没有出现必须迁移的 repo 内证据。现阶段更准确的判断是继续观察，不启动迁移。

只有在下面列出的触发条件真的出现后，才应重新评估是否升级到更强的持久化模型。触发条件未命中前，不应把这份文档解读成迁移任务。

## 评估范围

- 原子写底座：`core/data_store.py:37`
- API 层直接读写调用：`api/routes/data.py:35`、`api/routes/data.py:79`、`api/routes/data.py:113`、`api/routes/data.py:141`、`api/routes/data.py:160`、`api/routes/data.py:171`
- 业务反馈调用：`core/account_feedback.py:29`、`core/account_feedback.py:46`
- 共享状态 helper：`engine/actions/sdk_actions.py:589`、`engine/actions/sdk_actions.py:600`、`engine/actions/sdk_actions.py:627`
- 就近测试：`tests/test_data_store_path.py:6`、`tests/test_data_store_path.py:11`、`tests/test_sdk_actions_runtime.py:101`、`tests/test_sdk_actions_runtime.py:112`、`tests/test_sdk_actions_runtime.py:139`
- 就近文档：`docs/project_progress.md:9`、`docs/reference/功能原子化修复结果.md:25`、`docs/reference/功能原子化修复结果.md:37`、`docs/reference/功能原子化问题分类说明.md:65`、`docs/reference/sdk_actions_followup_assessment.md:48`

## 当前并发假设

当前仓库能被代码直接证明的假设很窄：

- `core/data_store.py` 的通用 JSON 写入能力提供的是单文件原子替换，见 `core/data_store.py:37`
- `api/routes/data.py` 里的账号池 `pop` 只在单进程内通过 `_accounts_lock` 串行化，见 `api/routes/data.py:12`、`api/routes/data.py:121`
- `core/account_feedback.py` 直接复用 `read_lines()` 和 `write_lines()`，本身没有额外锁，见 `core/account_feedback.py:29`、`core/account_feedback.py:46`
- 真正带有跨进程保护的 shared store 只在 `engine/actions/sdk_actions.py` 里的 `migration_shared.json` 路径上明确出现，见 `engine/actions/sdk_actions.py:591`、`engine/actions/sdk_actions.py:601`、`engine/actions/sdk_actions.py:629`

仓库里没有文档或测试声称 `core/data_store.py` 自身提供通用的多进程 read-modify-write 事务语义，所以这里不能把“当前 JSON 可用”扩写成“所有调用场景都已具备数据库级并发保证”。

## 当前已存在的保护

### 1. 原子写已经到位

- `write_json_atomic()` 先写临时文件，再 `fsync`，最后 `os.replace()`，这能把“写出半截 JSON”风险压下去，见 `core/data_store.py:37`
- `write_lines()` 和 `write_text()` 都复用这条路径，见 `core/data_store.py:69`、`core/data_store.py:83`
- `tests/test_data_store_path.py:11` 已固定 repeated updates 下 JSON 仍保持有效

### 2. 共享状态热点已经补了锁

- `engine/actions/sdk_actions.py` 为 `migration_shared.json` 增加了进程内 `_SHARED_STORE_LOCK`，见 `engine/actions/sdk_actions.py:25`、`engine/actions/sdk_actions.py:629`
- 同一段更新路径还包了一层 sibling lockfile + `fcntl.flock(LOCK_EX)`，见 `engine/actions/sdk_actions.py:596`、`engine/actions/sdk_actions.py:600`
- `tests/test_sdk_actions_runtime.py:112` 和 `tests/test_sdk_actions_runtime.py:139` 已覆盖线程内与跨进程 lost update 防护

### 3. 现有文档口径也是“已加固，但不是数据库”

- `docs/reference/功能原子化修复结果.md:33`、`docs/reference/功能原子化修复结果.md:35`、`docs/reference/功能原子化修复结果.md:44`、`docs/reference/功能原子化修复结果.md:45`、`docs/reference/功能原子化修复结果.md:46` 明确记录了原子写、同进程锁和跨进程文件锁
- `docs/reference/功能原子化修复结果.md:114`、`docs/reference/功能原子化修复结果.md:115`、`docs/reference/功能原子化修复结果.md:116` 也明确写了它仍不是数据库级共享状态方案
- `docs/reference/sdk_actions_followup_assessment.md:57` 认为 shared-store 当前更像边界观察点，不是 correctness 救火点

## 什么时候当前模型就不够了

下面这些信号只要出现任一项，就该把“继续观察”升级成正式重评，而不是继续默认 JSON store 足够。

### 1. workload shape 变了

- 同一个 shared JSON 文件开始承载高频写入，而不是当前这类轻量状态打点
- 多个 worker、进程或宿主机需要持续写同一份状态，而不仅是单机本地协调
- 新功能要求同一请求里连续更新多份 JSON 文件，并且这些更新必须一起成功或一起失败

### 2. coordination 要求变了

- 需要 compare-and-swap、版本校验、去重约束、唯一索引，或“只有一个消费者能拿到这条记录”这类更强语义
- 需要可查询的历史、审计、回滚，或按字段筛选聚合，而不是整个文件读回内存再处理
- 调用方开始依赖跨文件一致性，单个 `os.replace()` 已经不够表达业务边界

### 3. contention 证据真的出现了

- 出现 repo 可复现的 lost update、锁等待异常、锁文件竞争，或必须用重试才能掩盖共享写入冲突
- 测试开始需要为 shared store 加大量 sleep、轮询、重试，才能偶发通过
- 线上或集成环境记录到同一份 shared JSON 的明显争用，但现有 `_SHARED_STORE_LOCK` 加 `flock` 仍无法稳定收敛

### 4. ownership 边界变糊了

- `core/data_store.py` 的通用接口被越来越多 read-modify-write 业务直接复用，却没有把锁策略一起封装进去
- 除 `engine/actions/sdk_actions.py` 之外，又出现第二处、第三处自定义 shared-store 协调逻辑，说明共享状态协议开始分叉
- API 路由、业务 service、插件 helper 同时直接改同类 JSON 共享状态，导致谁负责序列化更新已经说不清

## 现在还不该启动迁移的原因

- 现有 repo 证据已经证明当前热点先靠原子写和锁做了加固，见 `docs/reference/功能原子化修复结果.md:25`、`docs/reference/功能原子化修复结果.md:37`
- 就近测试覆盖的是“保持 JSON 有效”和“避免已知丢写”，还没有出现失败证据指向现模型已失效，见 `tests/test_data_store_path.py:11`、`tests/test_sdk_actions_runtime.py:139`
- `docs/project_progress.md:9` 的项目状态也没有把 shared JSON store 列成当前 blocker
- 当前任务要求的是 watchpoint。仓库证据支持的结论也是 watchpoint，而不是隐式开启迁移

## 维护建议

- 新增 shared-state 写路径时，先判断能不能复用现有 helper，而不是直接在新位置裸做 read-modify-write
- 如果未来要重评，先补失败证据和 workload 形态说明，再决定是否进入数据库、单写者服务，或别的更强模型讨论
- 在触发条件出现前，保持当前结论不变：**watchpoint only，no migration now**
