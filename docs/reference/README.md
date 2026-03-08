# Reference Docs

这些文档属于底层能力参考资料与架构审查资料，主要用于适配器、SDK、RPA、运行时边界与复杂度控制核对。

说明：`atomicity_architecture_review.md` 保留的是“问题识别与拆分建议”视角；已经合入 `main` 的实际修复结果与 follow-up watchpoint 请同时参考 `docs/reference/功能原子化修复结果.md`、`docs/reference/功能原子化问题分类说明.md`、`sdk_actions_followup_assessment.md`、`shared_json_store_watchpoint.md` 与 `x_mobile_login_compression_watchpoint.md`。

- `complete_endpoint_matrix.md` - 从 PDF 提取后的综合接口矩阵，适合先快速看全貌
- `pdf_feature_usability_checklist.md` - 代码实现、运行时动作、测试证据之间的落地对照
- `hezi_sdk_atomic_mapping.md` - 最细粒度的 SDK `method/path -> client -> sdk.* action` 映射
- `atomicity_architecture_review.md` - 当前插件化与动作原子化设计的风险审查与拆分建议
- `sdk_actions_followup_assessment.md` - `sdk_actions` 当前复杂度与后续拆分阈值评估
- `shared_json_store_watchpoint.md` - shared JSON store 升级触发条件与非阻塞结论
- `x_mobile_login_compression_watchpoint.md` - `x_mobile_login` workflow 压缩重开条件
- `real_device_smoke_payloads.md` - 真机联调 payload 参考
- `hezi_sdk_smoke_payloads.md` - SDK 连通性与能力验证 payload 参考

推荐阅读顺序：

1. `atomicity_architecture_review.md`
2. `complete_endpoint_matrix.md`
3. `pdf_feature_usability_checklist.md`
4. `sdk_actions_followup_assessment.md`
5. `shared_json_store_watchpoint.md`
6. `x_mobile_login_compression_watchpoint.md`
7. `complete_endpoint_matrix.md`
8. `pdf_feature_usability_checklist.md`
9. `hezi_sdk_atomic_mapping.md`
