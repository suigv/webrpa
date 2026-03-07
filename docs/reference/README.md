# Reference Docs

这些文档属于底层能力参考资料与架构审查资料，主要用于适配器、SDK、RPA、运行时边界与复杂度控制核对。

- `complete_endpoint_matrix.md` - 从 PDF 提取后的综合接口矩阵，适合先快速看全貌
- `pdf_feature_usability_checklist.md` - 代码实现、运行时动作、测试证据之间的落地对照
- `hezi_sdk_atomic_mapping.md` - 最细粒度的 SDK `method/path -> client -> sdk.* action` 映射
- `atomicity_architecture_review.md` - 当前插件化与动作原子化设计的风险审查与拆分建议

推荐阅读顺序：

1. `atomicity_architecture_review.md`
2. `complete_endpoint_matrix.md`
3. `pdf_feature_usability_checklist.md`
4. `hezi_sdk_atomic_mapping.md`
