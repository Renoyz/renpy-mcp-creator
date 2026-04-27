# RenPy MCP Unified Design — 项目路线图

更新日期：2026-04-27

---

## 当前状态总览

| 维度 | 状态 |
|------|------|
| 核心流水线 | ✅ 全链路跑通：全自动链路可用；新增 Tier 4 v1 已纳入同一项目级流水线，并在失败场景具备回滚行为 |
| E2E 测试 | ✅ non-real E2E: 102 passed / 14 skipped；real-LLM E2E: 1 passed（当前会话验证，未展开任何未验证数字） |
| 代码质量 | ✅ P0-P3 全部解决，3 轮扫描验证 |
| 前端 Dashboard | ✅ React SPA 可用，workspace + chat panel + brief/outline 审核 + build/preview |
| 后端 API | ✅ FastAPI + WebSocket，REST 快照 API，Bridge IPC |
| 叙事质量 | 🔴 每章相同 emotional_arc，每场景仅 2 段对话，跨章重复"到达场景" |
| 已知 P1 问题 | 🟡 16 项已记录，未修复 |

---

## 文档结构

```
docs/
├── ROADMAP.md                    ← 你在这里
├── p1-remaining-issues.md        ← 待修复：16 个 P1 问题
├── narrative-improvement-plan.md ← 待执行：叙事完整性改进计划
│
├── plans/                        ← 实施计划
│   └── 2026-04-17-dashboard-backend-refactor-plan.md  (架构参考)
│
├── superpowers/specs/            ← 设计规格说明
│   ├── 2026-04-21-multi-chapter-style-consistency-design.md
│   ├── 2026-04-22-staged-requirements-refinement-design.md
│   └── 2026-04-23-agent-led-refinement-intake-design.md
│
├── <design-proposals>            ← 设计方案(待转化为实施计划)
│   ├── dual-agent-design.md
│   ├── refinement-interview-redesign.md
│   ├── stepwise-generation-design.md
│   └── ui-redesign-analysis.md
│
└── archive/                      ← 已完成的计划文档
    ├── [COMPLETED]-code-quality-convergence-plan.md
    ├── [COMPLETED]-e2e-diagnostic-repair-plan.md
    ├── [COMPLETED]-2026-04-24-e2e-diagnostic-tool.md
    ├── [PARTIAL]-2026-04-16-chat-image-build-persistence.md
    ├── [SUPERSEDED]-2026-04-15-core-feature-loop.md
    ├── [SUPERSEDED]-2026-04-23-phase7-round3-blueprint-freeze.md
    └── [SUPERSEDED]-2026-04-23-phase7-round4a-project-brief-intake.md
```

---

## 优先级排序的下一步行动

### 🔴 Tier 1 — 叙事完整性 (本周，投入~4h)

**目标**: 解决"生成的游戏为什么不好玩"

| Step | 内容 | 文件 | 预估 |
|------|------|------|------|
| 1 | 章节大纲字段按故事位置变化 (early/mid/late) | `chat_ws.py`, `fastapi_app.py` | 1h |
| 2 | 场景生成 prompt 注入章节大纲 + 连续性上下文 | `prototype_generation_service.py` | 2h |
| 3 | 每场景 4-8 段对话 + 软校验 | `prototype_generation_service.py` | 1h |

**预期效果**: 每章有不同的情感弧线 → 场景有完整的对话交换 → 跨章节不再重复

详见: `narrative-improvement-plan.md`

---

### 🟡 Tier 2 — P1 问题修复 (本周~下周，投入~5h)

**目标**: 消除静默失败、阻塞 I/O、重复代码

| 轮次 | 内容 | 预估 |
|------|------|------|
| 第1轮 | 写入失败吞没 + 重复 `_write_build_status` 统一 + `self.draft = None` 加日志 | 2h |
| 第2轮 | 同步 I/O 异步化 + Windows `SystemRoot` 动态获取 | 1h |
| 第3轮 | 其余 13 处 `except Exception: pass` + logger.warning | 2h |

**预期效果**: 线上问题可定位、高并发无阻塞、非 C: 盘 Windows 正常工作

详见: `p1-remaining-issues.md`

---

### 🟠 Tier 3 — 自适应摄入对话 (下周~下下周，投入~3-5天)

**目标**: 用 LLM 驱动的自适应对话替代硬编码 2 轮固定问题

**核心改动**:
- Propose-then-converge 行为规则
- "我不知道" → AI 提供备选方案
- 跨卡片一致性检查
- `proposal_history` 追踪

**预期效果**: AI 像创意伙伴一样工作，不再被固定问题框住

详见: `refinement-interview-redesign.md`

---

### 🟠 Tier 4 — 分步生成 (v1 已完成，后续 hardening/v1.1)

**状态**: 已完成 v1（commit f5a980b）。后续任务聚焦 v1.1 hardening 与边界稳定性。

**v1 已实现能力**:
1. `generation-state` 持久化与恢复
2. scene outline start / confirm
3. 角色与背景：upload / accept / confirm
4. script preview / commit
5. staging 写入与回滚
6. 用户导入路径（uploaded slot）完整入链路（同一资产生命周期）

**v1.1（可选 hardening）**:
- 同路径重入时与历史稳定资产覆盖策略的边界加固
- 上传校验失败与恢复链路的可观测性增强
- 非法文件/恶意路径场景的更细粒度错误提示与度量

详见: `stepwise-generation-design.md`

---

### 🔵 Tier 5 — 双代理质量门 (下月，投入~2-3周)

**目标**: 每个生成内容都经过系统性质检

**五维审计**: 连续性、蓝图保真度、资源覆盖、基调对齐、可玩性

**预期效果**: 质量可量化——"第 3 章角色 A 性格锚点漂移了"不是感觉，是数据

详见: `dual-agent-design.md`

---

### 🔵 Tier 6 — Dashboard UI 重构 (下月+，投入~3-5周)

**目标**: UI 从 IDE 风格改为 AI 驱动的"进度驾驶舱"

**6 个问题**: P1 角色编辑器持久化、P2 角色引用一致性、P3 多章节视觉隔离、P4 sidebar 场景总数、P5 build/preview 按章节 scoped、P6 StoryMap 用 React Flow 替代 iframe

详见: `ui-redesign-analysis.md`

---

## 完成的历史（已归档至 archive/）

| 计划 | 完成日期 | 成果 |
|------|---------|------|
| 代码质量收敛 | 2026-04-26 | P0-P3 全部解决，3 轮扫描验证 |
| E2E 诊断工具 | 2026-04-26 | 27/27 测试通过，全链路 104s PASS |
| E2E 修复 (R1-R6) | 2026-04-26 | 所有 6 个盲点修复 |
| 聊天图片 & Build 持久化 | 2026-04-26 | 图片渲染 ✓, build 状态持久化 ✓ |
| 核心功能循环 | 2026-04-26 | 全链路可用 (被后续计划取代) |
| Blueprint Freeze | 2026-04-26 | 功能可用 (被后续计划取代) |
| Project Brief Intake | 2026-04-26 | 功能可用 (被后续计划取代) |

---

## 维护规则

1. **新设计** → 放入 `docs/` 或 `docs/superpowers/specs/`
2. **实施计划** → 放入 `docs/plans/`
3. **完成后** → 移到 `docs/archive/`，前缀 `[COMPLETED]-`
4. **被取代** → 移到 `docs/archive/`，前缀 `[SUPERSEDED]-`
5. **每次迭代后更新本文件**
