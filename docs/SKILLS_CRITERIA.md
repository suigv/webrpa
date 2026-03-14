# Skills vs. Low-Level Actions: 分类与治理规范

## 1. 核心矛盾
WebRPA 的 `ActionRegistry` 目前收集了超过 150 个原子动作。将所有动作全量暴露给 AI Agent 会导致以下问题：
1. **Prompt 污染**：动作过多导致上下文溢出，AI 难以选择。
2. **意图不明**：许多动作（如 `sdk.get_api_version`）是基建细节，不具备业务语义。
3. **脆弱性**：底层 RPC 接口变动频繁，不适合作为上层 Skill 的契约。

## 2. 分类标准

### 2.1 技能 (Skills) - **暴露给 AI**
具有明确业务含义，且参数和输出相对稳定的动作。
- **特征**：
    - 语义化：如 `app.open`, `ui.click`, `ai.vlm_evaluate`。
    - 结果导向：执行后有明确的状态变化或数据返回。
    - 稳定性：契约（Schema）一旦定义，向下兼容。
- **治理**：必须带有完整的 `ActionMetadata`，并标记 `tags=["skill"]`。

### 2.2 低层动作 (Low-Level Actions) - **内部/脚本使用**
用于环境准备、协议转换或极低层硬件操作。
- **特征**：
    - 工具化：如 `mytos.query_s5_proxy`, `sdk.list_image_tars`, `sdk.get_ssh_ws_url`。
    - 过程化：仅作为复合动作的一部分。
    - 高耦合：与特定硬件或协议版本紧密相关。
- **治理**：可以没有 Schema，标记 `tags=["internal"]`。

### 2.3 复合技能 (Composite Skills / Plugins) - **推荐演进方向**
由多个原子动作组合而成的业务逻辑。
- **例子**：`x.login` (包含 `app.open` + `ui.input_text` + `ui.click`)。
- **治理**：这是 Skills 化的终极目标，应通过插件系统实现。

## 3. 治理执行路线

1. **Tagging (打标)**：在 `ActionMetadata` 中引入 `tags` 字段。
2. **Discovery Filter (过滤发现)**：
    - `/api/engine/schema` 默认仅返回带有 `skill` 标签的动作。
    - AI Agent 获取的“技能书”仅包含 `tags=["skill"]` 的条目。
3. **Promotion (晋升机制)**：
    - 只有经过验证、具备业务价值的内部动作，在补齐元数据并打上 `skill` 标签后，才能晋升为技能。

## 4. 重点关注
> [!IMPORTANT]
> 并非所有的 `Action` 都要 Skills 化。过度 Skills 化会增加系统的熵。我们应该追求 **"精简而强大"** 的技能集。
