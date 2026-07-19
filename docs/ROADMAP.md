# RenPy MCP Creator 路线图

更新日期：2026-07-19

## 当前状态

| 维度 | 状态 |
|---|---|
| 核心流水线 | 可运行：项目创建 → intake → brief → outline → blueprint freeze → 多章节场景 → 资产 → 脚本 → build/preview |
| 历史真实 E2E | 2026-04 已完成一次真实模型全流程验证：14/14 阶段，约 132 秒；这不是当前每次提交的自动保证 |
| 当前本地验证 | 2026-07-19：unit 478 passed / 1 skipped；chat_engine 14 passed；integration 417 passed / 0 failed；e2e 仅 collect-only（144 collected，未全量运行）；Dashboard build + 12 files / 46 tests（2026-07-13）；Desktop build + 3 files / 6 tests（2026-07-13） |
| 桌面交付 | Electron/PyInstaller 源码已存在；NSIS 安装包与全新机器 smoke test 已延期，先以 pip/uv 安装路径发布 |
| 运行环境 | 仅 Python 3.11（3.12+ 被 rembg/numba 依赖链阻塞，`requires-python` 已设为 `<3.12`）；Windows 为主 |
| 产品验证 | 尚无外部用户；开源发布后以 Issue/star/使用报告等软信号衡量 |
| 版本 | 0.1.0 development preview |

## 当前决策

项目转为开源（MIT）、非商业化维护：以“可发布、可维护、可验证的 Ren'Py 工程工具”为定位公开发布，由社区反馈驱动后续迭代。

近期不以一次生成更多文本、增加更多模型供应商或继续扩大 Dashboard 为目标。

## 优先级

### P0：开源发布与社区反馈

- 保持仓库、依赖锁、许可证、环境模板和文档一致。
- 完成 GitHub 公开发布与 v0.1.0 tag。
- 通过社区渠道收集试用反馈（Issue、star、实际使用报告）。
- 保持本地优先、BYOK/self-hosted，不引入托管服务依赖。
- Windows 安装包与全新机器 smoke test 延期：先以 pip/uv 安装路径发布，由用户需求驱动恢复。

### P1：修复当前可靠性缺口

2026-07-19 已完成：

- integration 4 个失败全部修复（验证：`python -m pytest tests/integration -q` → 417 passed / 0 failed）：upload 测试补齐冻结蓝图前置并对背景移除打桩；mock build 输出路径断言改为相对 workspace 解析。
- 预览子进程泄漏修复：FastAPI lifespan 关闭时 `stop_all()`；HTTP 路由与 MCP 工具共用 `get_shared_preview_manager()`；integration 预览测试统一打桩；e2e start/stop 改为 try/finally，Windows 用 `taskkill /T /F` 清理进程树。修复后实测不再新增 `http.server` 残留。
- 发布阻塞修复：`httpx` 移入运行时依赖（uv.lock 已刷新）；`vn-creator start` 接入 SDK 自动下载（失败仅告警不阻塞启动）；`_redact_local_paths` 覆盖 SDK 路径；`start.bat` 增加 dashboard/dist 缺失提示。

仍开放：

- 全新机器 smoke test（PyInstaller hiddenimports、rembg 首次模型下载）未验证。
- e2e 全量（Playwright）本轮未运行，仅 collect-only。

### P2：工程差异化（由社区需求拉动）

以下工作不再预设排期，由真实 Issue 和用户反馈拉动；没有需求信号时不主动开发：

1. GameIR v1：结构化权威源、schema version 和 validator。
2. Asset Manifest Protocol：统一 required/candidate/accepted 生命周期及本地 provider hook。
3. Generated/User Ownership：generated/custom 边界、dirty detection、preview diff 和 no-overwrite policy。
4. Ren'Py compiler/diagnostics：label、jump、choice、变量和资产引用校验。

详见 [视觉小说工程中间件目标差距分析](vn-engineering-middleware-gap-analysis.md)。

## 明确不做

- 双 Agent Creator/Auditor 质量门。
- 新一轮大规模 Dashboard 重构。
- 更多 LLM 或图像供应商。
- 完整分支图编辑器、语音和 BGM 自动生成。
- 托管 SaaS 与计费系统。

项目转为开源维护模式后，以上方向整体排除。双 Agent 方案保留为[未来设计](dual-agent-design.md)，仅作历史参考，不构成实施承诺。

## 维护模式

项目以开源形式维护，不设商业化指标：

- 迭代由真实 Issue 拉动；没有用户信号时不预先扩展功能。
- 真实 LLM E2E 仅在需要时手动触发，不作为每次提交的门槛。
- 若长期（约 6 个月）没有任何外部使用信号，将仓库归档为参考实现，停止主动维护。

## 文档状态

- [文档索引](README.md)
- [当前产品方向](vn-engineering-middleware-gap-analysis.md)
- [未来双 Agent 设计](dual-agent-design.md)
- [历史归档](archive/)
- [本次仓库清理规格](superpowers/specs/2026-07-12-repository-cleanup-design.md)
- [本次仓库清理计划](superpowers/plans/2026-07-12-repository-cleanup-plan.md)
