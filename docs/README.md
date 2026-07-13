# 文档索引

**docs/ROADMAP.md** 是项目当前状态与优先级的唯一权威来源。旧计划中的完成框、测试数字和“下一步”仅代表当时上下文。

## 当前文档

- [ROADMAP.md](ROADMAP.md)：当前状态、已知问题、优先级与止损标准。
- [vn-engineering-middleware-gap-analysis.md](vn-engineering-middleware-gap-analysis.md)：从原型生成器走向可维护 Ren'Py 工程中间件的差距分析。
- [dual-agent-design.md](dual-agent-design.md)：延期的 Creator/Auditor 未来设计，不是当前实施阶段。
- [仓库清理规格](superpowers/specs/2026-07-12-repository-cleanup-design.md)：本次目录、文档和 Git 清理的批准边界。
- [仓库清理实施计划](superpowers/plans/2026-07-12-repository-cleanup-plan.md)：本次清理的可验证执行步骤。

## 历史归档

**archive/** 保存已经完成、部分完成或被取代的设计和计划：

- **[COMPLETED]-**：对应能力已经实现或验证。
- **[PARTIAL]-**：只实现了明确记录的部分范围。
- **[SUPERSEDED]-**：设计已被后续方案取代。
- **archive/prompts/**：历史 Kimi TDD 执行提示。

归档文档不是当前需求来源。若归档文档与 ROADMAP、代码或测试冲突，以当前代码、当前测试和 ROADMAP 为准。

## 维护规则

1. 当前状态只更新 **ROADMAP.md**。
2. 新设计写入 **docs/superpowers/specs/**，批准后再编写 **docs/superpowers/plans/**。
3. 完成或取代后移入 **docs/archive/** 并添加状态前缀。
4. 文档不得包含真实 API key、用户绝对路径或未验证的通过数字。
5. 每次声称功能完成时，必须同时记录实际运行的验证命令与结果。
