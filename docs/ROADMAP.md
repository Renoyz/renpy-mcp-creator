# RenPy MCP Creator 路线图

更新日期：2026-07-13

## 当前状态

| 维度 | 状态 |
|---|---|
| 核心流水线 | 可运行：项目创建 → intake → brief → outline → blueprint freeze → 多章节场景 → 资产 → 脚本 → build/preview |
| 历史真实 E2E | 2026-04 已完成一次真实模型全流程验证：14/14 阶段，约 132 秒；这不是当前每次提交的自动保证 |
| 当前本地验证 | 2026-07-13 清理后：unit 466 passed / 1 skipped；chat_engine 14 passed；integration 413 passed / 4 failed；Dashboard build + 12 files / 46 tests；Desktop build + 3 files / 6 tests |
| 桌面交付 | Electron/PyInstaller 源码已存在；稳定 NSIS 安装包和安装后 smoke test 尚未完成 |
| 产品验证 | 尚无可核验的外部用户完成率、复用率或付费意愿数据 |
| 版本 | 0.1.0 development preview |

## 当前决策

项目继续方式从“扩展更多 AI 功能”调整为“先完成可发布、可维护、可验证的 Ren'Py 工程工具”。

近期不以一次生成更多文本、增加更多模型供应商或继续扩大 Dashboard 为目标。优先证明用户能独立完成一次真实项目，并能在人工精修后安全地继续增量生成。

## 优先级

### P0：发布卫生与真实用户验证

- 保持仓库、依赖锁、许可证、环境模板和文档一致。
- 完成 Windows 安装包及全新机器 smoke test。
- 找到 8–10 名真实 Ren'Py 创作者，验证端到端完成率、二次使用率和支持成本。
- 保持本地优先、BYOK/self-hosted，避免把模型成本和私有素材强制放到托管服务。

### P1：修复当前可靠性缺口

当前 integration suite 有两个失败簇：

1. **test_stepwise_generation_import_upload.py** 的 3 个测试与当前 blueprint 前置条件不一致。
2. **test_ws_chat_blueprint.py::test_auto_build_mock_output_path_matches_api_endpoint** 的 mock build 相对路径解析不一致。

集成测试还可能遗留测试专用 **python -m http.server** 预览子进程。修复时必须保留项目级路径隔离和 rollback 行为。

### P2：建立真正的工程差异化

用户验证成立后，按以下顺序推进：

1. GameIR v1：结构化权威源、schema version 和 validator。
2. Asset Manifest Protocol：统一 required/candidate/accepted 生命周期及本地 provider hook。
3. Generated/User Ownership：generated/custom 边界、dirty detection、preview diff 和 no-overwrite policy。
4. Ren'Py compiler/diagnostics：label、jump、choice、变量和资产引用校验。

详见 [视觉小说工程中间件目标差距分析](vn-engineering-middleware-gap-analysis.md)。

## 明确延期

- 双 Agent Creator/Auditor 质量门。
- 新一轮大规模 Dashboard 重构。
- 更多 LLM 或图像供应商。
- 完整分支图编辑器、语音和 BGM 自动生成。
- 托管 SaaS 与计费系统。

这些工作只有在真实用户验证通过、核心工程边界稳定后才能重新排期。双 Agent 方案保留为[未来设计](dual-agent-design.md)，不是当前实施阶段。

## 4–6 周继续/停止标准

继续投入至少需要满足：

- 至少 5 名测试用户能在不依赖开发者代操作的情况下完成全流程。
- 至少 3 名用户在两周内创建第二个项目。
- 至少 2 名用户愿意进入付费试点或持续赞助。
- 人工修改后的再次生成没有覆盖事故。
- 单名用户的支持成本低于 1 小时。

若其中两项未达到，停止商业化扩张，将项目收缩为开源 Ren'Py MCP/工程工具包。

## 文档状态

- [文档索引](README.md)
- [当前产品方向](vn-engineering-middleware-gap-analysis.md)
- [未来双 Agent 设计](dual-agent-design.md)
- [历史归档](archive/)
- [本次仓库清理规格](superpowers/specs/2026-07-12-repository-cleanup-design.md)
- [本次仓库清理计划](superpowers/plans/2026-07-12-repository-cleanup-plan.md)
