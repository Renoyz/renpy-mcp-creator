# [ARCHIVED - COMPLETED] e2e-diagnostic-repair-plan

> **Date archived:** 2026-04-26
> **Status:** COMPLETED
> **Reason:** R1-R6 all repaired and verified. Full real-LLM E2E test passes (104s, 14/14 stages).
>
> This document has been moved to . Original content preserved below.

---

# E2E 诊断工具修复计划

## 目标

修复 `tests/e2e/test_full_game_creation_real_llm_playwright.py` 中的 4 个系统性盲点，使诊断工具能够可信地覆盖从项目创建到 Build 完成的全部 8 个阶段。

## 修复前状态

| 流水线阶段 | 能否发现真实问题？ | 根因 |
|-----------|-------------------|------|
| 1. 项目创建 | 能 | — |
| 2. Intake 对话 | 能 | — |
| 3. Brief 确认 | 勉强 | 800ms 竞态导致频繁 API 回退 |
| 4. Outline 确认 | 勉强 | 同上 |
| 5. Freeze | 能 | — |
| 6. Scene-package 生成 | **不能** | `page.reload()` 中断 `runFreezeAutoGenerationChain` |
| 7. Prototype 生成 | **不能** | `page.reload()` 中断 chain + mock build 不检查文件 |
| 8. Build 完成 | **不能** | "Preview" 文本始终可见，假阳性 |

---

## 修复项

### R1: 用 postFreezeFlow 等待替代 page.reload()

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**函数:** `_run_freeze_and_build_stage`
**严重程度:** 高 — 跳过 3 个 pipeline 阶段

**当前代码（问题）:**
```python
freeze_btn.click()
_wait_for_blueprint_file(blueprint_path)   # 只等 freeze
page.reload()                               # 杀死 runFreezeAutoGenerationChain
page.wait_for_timeout(1500)
```

**修复后:**
```python
freeze_btn.click()

# 等待 auto-generation chain 全部完成
# postFreezeFlow.status === "success" 时前端渲染:
#   data-testid="post-freeze-status" + text="Scene packages and prototype scripts are ready"
# 或 postFreezeFlow.status === "failed" 时渲染错误消息
post_freeze_status = page.locator("[data-testid='post-freeze-status']")
post_freeze_success = post_freeze_status.filter(has_text="Scene packages and prototype scripts are ready")
post_freeze_failed = post_freeze_status.filter(has_text="failed").or_(
    post_freeze_status.locator("text=Error").or_(post_freeze_status.locator("text=error"))
)
post_freeze_success.or_(post_freeze_failed).first.wait_for(state="visible", timeout=120000)

if post_freeze_failed.count() > 0:
    _snap(page, "12b_post_freeze_failed", writer=artifacts)
    raise AssertionError(
        f"Post-freeze auto-generation chain failed: {post_freeze_status.text_content()}"
    )

_snap(page, "12_blueprint_frozen", writer=artifacts)
# 不再 reload — 前端状态完整保留
```

**验证:** 故意引入 scene-package 端点返回 500 → 诊断工具应报告 FAIL + 截图 "12b_post_freeze_failed"

---

### R2: 用 data-testid 替代 "Preview" 假阳性

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**函数:** `_run_freeze_and_build_stage`
**严重程度:** 高 — Build 失败永远不可见

**当前代码（问题）:**
```python
page.locator("text=Build complete").or_(page.locator("text=Preview")).first.wait_for(
    state="visible", timeout=120000,
)
```

**修复后:**
```python
# 等待 Build 状态变为 success（按钮文本 "Build OK"）
# 或 data-testid="build-status" 内容不为空
build_ok = page.locator("button", has_text="Build OK")
build_failed = page.locator("button", has_text="Retry Build")
build_status = page.locator("[data-testid='build-status']")

build_ok.or_(build_failed).first.wait_for(state="visible", timeout=120000)

if build_failed.count() > 0:
    status_text = build_status.text_content() or "(no build status text)"
    _snap(page, "14b_build_failed", writer=artifacts)
    raise AssertionError(f"Build failed: {status_text}")

_snap(page, "14_build_complete", writer=artifacts)
```

**验证:** 故意引入 build 端点返回错误 → 诊断工具应报告 FAIL + 截图 "14b_build_failed"

---

### R3: 用 expect 等待替代 800ms 硬编码

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**函数:** `_try_complete_brief_review_ui`, `_try_complete_outline_review_ui`
**严重程度:** 中 — 导致 UI confirm 路径频繁误判为失败

**当前代码（问题）:**
```python
for _ in range(20):
    confirm_buttons = _pending_confirm_buttons(page)
    if confirm_buttons.count() == 0:
        break
    confirm_buttons.first.click()
    page.wait_for_timeout(800)           # 硬编码 800ms
```

**修复后:**
```python
for _ in range(20):
    confirm_buttons = _pending_confirm_buttons(page)
    if confirm_buttons.count() == 0:
        break
    btn = confirm_buttons.first
    btn.click()
    # 等待该按钮变为 disabled 或文本变为 "Confirmed"，确认操作已提交
    btn.locator("..").locator("button[disabled]").or_(
        page.locator("button[disabled]")
    ).first.wait_for(state="visible", timeout=15000)
    # 再等待按钮恢复为非 disabled（"Confirm" 或 "Confirmed" 出现），确认操作已完成
    expect(page.locator("button:not([disabled])").filter(
        has_text=re.compile(r"^(Confirm|Confirmed)$")
    ).first).to_be_visible(timeout=15000)
```

**验证:** 在 `HYBRID_RECOVERY` 模式下，正常网络环境下 confirm 应全部通过 UI 路径，不回退到 API

---

### R4: 清理幽灵选择器

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**严重程度:** 低 — 代码卫生

**删除/修改项:**

| 位置 | 当前 | 修复 |
|------|------|------|
| `_run_freeze_and_build_stage` | `.or_(page.locator("text=Generate Game"))` | 删除 `.or_()` 分支 |
| `_run_freeze_and_build_stage` | `text=Build complete` | 替换为 `button:has-text("Build OK")` |
| `_run_intake_stage` | `text=Generating` | 此选择器不在 build 上下文中，保留但加注释说明适用范围 |

---

### R5: 添加 JS 控制台错误捕获（额外改进）

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**严重程度:** 中 — 当前完全不可见

**新增代码（在 Runner init 或 start_real_llm_server 之后）:**
```python
page.on("pageerror", lambda err: artifacts.write_text(
    "browser_errors", "console", f"{err}\n", suffix=".log"
))
```

---

### R6: 新增测试入口点

**文件:** `tests/e2e/test_full_game_creation_real_llm_playwright.py`
**严重程度:** 中 — 模式覆盖不完整

**新增:**
```python
def test_full_game_creation_with_real_llm_ui_diagnostic(
    page: Page, e2e_workspace: Path,
) -> None:
    """UI_ONLY_DEBUG 模式：禁止 API 回退，暴露所有 UI bug。CI 使用此入口。"""
    ...

def test_full_game_creation_with_real_llm_and_real_build(
    page: Page, e2e_workspace: Path,
) -> None:
    """REAL_BUILD_ACCEPTANCE 模式：真构建，验证 prototype 可玩。手动触发。"""
    ...
```

---

## 执行顺序

```
R4 (幽灵选择器清理) → R1 (postFreezeFlow 等待) → R2 (Build OK 检测)
       ↓
R3 (expect 替代 800ms)
       ↓
R5 (JS 错误捕获)
       ↓
R6 (新增入口点)
```

R4 优先执行因为清理后 R1/R2 的修改更清晰。R1 和 R2 必须在 R3 之前，因为 confirm 循环的改进依赖 postFreezeFlow 完成后的页面状态。

## 验证标准

修复后运行以下命令应全部通过（`HYBRID_RECOVERY` 模式下）:

```powershell
# 专项诊断测试
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "artifact_writer or ui_only_mode or hybrid_recovery or brief_tab_route_failure or outline_tab_route_failure or summary_markdown or backend_logs" -q

# UI 诊断模式（应失败——因为我们知道 UI 有已知问题）
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm_ui_diagnostic -q -s

# Hybrid recovery 模式（应通过——API 回退弥补 UI 问题，但不应掩盖 post-freeze/build 问题）
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -q -s

# 回归测试
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -q
uv run pytest tests/integration/test_ws_chat_blueprint.py -q
```

## 风险

| 风险 | 缓解 |
|------|------|
| `postFreezeFlow` 等待超时（120s）在真实 LLM 下可能不够 | R1 中捕获超时后截图 + 记录当前 postFreezeFlow 状态，NOT 静默通过 |
| Build OK 依赖 `runFreezeAutoGenerationChain` 成功 | R1 确保 chain 完成后才进入 build 阶段 |
| `expect` 等待在慢 CI 上可能仍然超时 | 用 `timeout=15000` 替代 `timeout=5000`，CI 环境通常稳定 |
