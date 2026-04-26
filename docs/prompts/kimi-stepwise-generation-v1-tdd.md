# Kimi 执行 — 分步生成 MVP v1 (TDD)

**目标**: 将 post-freeze 流水线从一键生成改为 4 步可干预流程。

**设计方**: Claude/DeepSeek
**执行方**: Kimi
**参考设计**: `docs/stepwise-generation-concrete-design.md`

---

## 前置条件

```bash
cd D:/renpy-mcp-unified-design
python -m pytest tests/integration/test_prototype_generation.py -x -q  # 基线 68 PASS
cd dashboard && npm run build  # 前端可构建
```

---

# Part A: 后端 — 步骤控制 + WS 消息 (TDD)

## Step A1: 步骤控制器

### 🔴 RED

**新建**: `tests/unit/test_generation_step_controller.py`

```python
"""TDD: GenerationStepController for step-wise generation pipeline."""
import pytest


def test_step_controller_initializes_at_step_1():
    """New controller starts at step 1 (scene_outline)."""
    from renpy_mcp.services.prototype_orchestration import GenerationStepController
    ctrl = GenerationStepController(project_name="test")
    assert ctrl.current_step == 1
    assert ctrl.step_name == "scene_outline"


def test_step_controller_advances_to_next_step():
    """After confirming a step, advance to next."""
    from renpy_mcp.services.prototype_orchestration import GenerationStepController
    ctrl = GenerationStepController(project_name="test")
    ctrl.confirm_step()
    assert ctrl.current_step == 2
    assert ctrl.step_name == "character_assets"


def test_step_controller_cannot_skip_steps():
    """Only the current step can be confirmed; skipping raises."""
    from renpy_mcp.services.prototype_orchestration import GenerationStepController
    ctrl = GenerationStepController(project_name="test")
    with pytest.raises(ValueError, match="not the current step"):
        ctrl.confirm_step(step=4)


def test_step_controller_tracks_confirmed_assets():
    """Controller tracks which characters/backgrounds are confirmed."""
    from renpy_mcp.services.prototype_orchestration import GenerationStepController
    ctrl = GenerationStepController(project_name="test")
    ctrl.confirm_character("char_1")
    ctrl.confirm_character("char_2")
    assert ctrl.confirmed_characters == {"char_1", "char_2"}
    assert not ctrl.all_characters_confirmed(["char_1", "char_2", "char_3"])
    ctrl.confirm_character("char_3")
    assert ctrl.all_characters_confirmed(["char_1", "char_2", "char_3"])


def test_step_controller_sets_state_on_step_start():
    """Starting a step sets its state to 'active'."""
    from renpy_mcp.services.prototype_orchestration import GenerationStepController
    ctrl = GenerationStepController(project_name="test")
    ctrl.start_step(1)
    assert ctrl.step_state == "active"


def test_manifest_writes_generation_step():
    """Manifest records current generation_step for recovery."""
    import json
    from pathlib import Path
    from renpy_mcp.services.prototype_orchestration import GenerationStepController

    ctrl = GenerationStepController(project_name="test")
    manifest = ctrl._build_manifest()
    assert manifest["generation_step"] == "scene_outline"
    assert manifest["current_step"] == 1
```

运行:
```bash
python -m pytest tests/unit/test_generation_step_controller.py -v
# 必须 ALL FAIL — GenerationStepController 不存在
```

### 🟢 GREEN

**文件**: `src/renpy_mcp/services/prototype_orchestration.py`

新增 `GenerationStepController` 类:

```python
class GenerationStepController:
    """Controls the 4-step generation pipeline after blueprint freeze.

    Steps:
      1. scene_outline   — review scene packages
      2. character_assets — review/retry character sprites
      3. background_assets — review/retry background images
      4. script_assembly  — preview scripts before writeback
    """

    STEP_NAMES = {
        1: "scene_outline",
        2: "character_assets",
        3: "background_assets",
        4: "script_assembly",
    }

    def __init__(self, project_name: str) -> None:
        self.project_name = project_name
        self.current_step = 1
        self.step_state = "idle"  # idle | active | complete
        self.confirmed_characters: set[str] = set()
        self.confirmed_backgrounds: set[str] = set()

    @property
    def step_name(self) -> str:
        return self.STEP_NAMES[self.current_step]

    def start_step(self, step: int) -> None:
        if step != self.current_step:
            raise ValueError(f"Cannot start step {step}; current step is {self.current_step}")
        self.step_state = "active"

    def confirm_step(self, step: int | None = None) -> None:
        target = step or self.current_step
        if target != self.current_step:
            raise ValueError(f"Step {target} is not the current step ({self.current_step})")
        if self.current_step < 4:
            self.current_step += 1
            self.step_state = "idle"
        else:
            self.step_state = "complete"

    def confirm_character(self, char_id: str) -> None:
        self.confirmed_characters.add(char_id)

    def confirm_background(self, location: str) -> None:
        self.confirmed_backgrounds.add(location)

    def all_characters_confirmed(self, all_char_ids: list[str]) -> bool:
        return self.confirmed_characters.issuperset(all_char_ids)

    def all_backgrounds_confirmed(self, all_locations: list[str]) -> bool:
        return self.confirmed_backgrounds.issuperset(all_locations)

    def _build_manifest(self) -> dict:
        return {
            "generation_step": self.step_name,
            "current_step": self.current_step,
            "step_state": self.step_state,
            "confirmed_characters": sorted(self.confirmed_characters),
            "confirmed_backgrounds": sorted(self.confirmed_backgrounds),
        }
```

### ✅ 验证

```bash
python -m pytest tests/unit/test_generation_step_controller.py -v  # 6 PASS
```

---

## Step A2: WebSocket 步骤控制消息

### 🔴 RED

**新建**: `tests/unit/test_generation_ws_messages.py`

```python
"""TDD: WebSocket message builders for step-wise generation."""
import json


def test_build_generation_step_message():
    """Message emitted when a generation step becomes active."""
    from renpy_mcp.services.prototype_orchestration import _build_step_message
    msg = _build_step_message(step=1, status="active")
    assert msg["type"] == "generation_step"
    assert msg["step"] == 1
    assert msg["step_name"] == "scene_outline"
    assert msg["status"] == "active"


def test_build_character_asset_result_message():
    """Message emitted when a character sprite is ready."""
    from renpy_mcp.services.prototype_orchestration import _build_character_result_message
    msg = _build_character_result_message(
        character_id="char_1",
        sprites={"normal": "/assets/char_1_normal.png", "happy": "/assets/char_1_happy.png", "sad": "/assets/char_1_sad.png"},
    )
    assert msg["type"] == "character_asset_result"
    assert msg["character_id"] == "char_1"
    assert "normal" in msg["sprites"]


def test_build_background_asset_result_message():
    """Message emitted when a background image is ready."""
    from renpy_mcp.services.prototype_orchestration import _build_background_result_message
    msg = _build_background_result_message(
        location="bg_ruins",
        image="/assets/bg_ruins.png",
    )
    assert msg["type"] == "background_asset_result"
    assert msg["location"] == "bg_ruins"


def test_build_script_preview_message():
    """Message emitted with assembled script preview."""
    from renpy_mcp.services.prototype_orchestration import _build_script_preview_message
    msg = _build_script_preview_message(
        files=[{"name": "prototype_ch1.rpy", "content": "label start:\n    return"}]
    )
    assert msg["type"] == "script_preview"
    assert len(msg["files"]) == 1
    assert msg["files"][0]["name"] == "prototype_ch1.rpy"
```

运行:
```bash
python -m pytest tests/unit/test_generation_ws_messages.py -v
# 必须 ALL FAIL — 函数不存在
```

### 🟢 GREEN

**文件**: `src/renpy_mcp/services/prototype_orchestration.py`

新增 4 个纯函数:

```python
def _build_step_message(step: int, status: str) -> dict:
    return {
        "type": "generation_step",
        "step": step,
        "step_name": GenerationStepController.STEP_NAMES.get(step, "unknown"),
        "status": status,
    }

def _build_character_result_message(character_id: str, sprites: dict) -> dict:
    return {
        "type": "character_asset_result",
        "character_id": character_id,
        "sprites": sprites,
    }

def _build_background_result_message(location: str, image: str) -> dict:
    return {
        "type": "background_asset_result",
        "location": location,
        "image": image,
    }

def _build_script_preview_message(files: list[dict]) -> dict:
    return {
        "type": "script_preview",
        "files": files,
    }
```

### ✅ 验证

```bash
python -m pytest tests/unit/test_generation_ws_messages.py -v  # 4 PASS
```

---

## Step A3: 集成 — 步骤控制器接入 WS handler

### 🔴 RED

**追加到** `tests/unit/test_generation_step_controller.py`:

```python
def test_controller_integrates_with_post_freeze_flow():
    """After freeze completes, controller is created and step 1 starts."""
    from renpy_mcp.services.prototype_orchestration import (
        GenerationStepController,
        _build_step_message,
    )

    ctrl = GenerationStepController(project_name="test")
    ctrl.start_step(1)

    # Simulate the WS message that would be sent after freeze
    msg = _build_step_message(step=ctrl.current_step, status=ctrl.step_state)
    assert msg["type"] == "generation_step"
    assert msg["step"] == 1
    assert msg["status"] == "active"
```

### 🟢 GREEN — 无需新代码

测试直接 PASS（函数已在 Step A1/A2 实现），验证集成正确。

### ✅ 验证

```bash
python -m pytest tests/unit/test_generation_step_controller.py tests/unit/test_generation_ws_messages.py -v  # ALL PASS
```

---

# Part B: 前端 — GenerationWorkspace 页面 (MVP)

## Step B1: 步骤指示器组件

### 🔴 RED — 前端测试

**新建**: `dashboard/src/components/generation/__tests__/StepIndicator.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import { StepIndicator } from '../StepIndicator';

test('renders 4 steps', () => {
  render(<StepIndicator currentStep={1} completedSteps={new Set()} />);
  expect(screen.getByText('场景')).toBeInTheDocument();
  expect(screen.getByText('角色')).toBeInTheDocument();
  expect(screen.getByText('背景')).toBeInTheDocument();
  expect(screen.getByText('脚本')).toBeInTheDocument();
});

test('current step is highlighted', () => {
  render(<StepIndicator currentStep={2} completedSteps={new Set()} />);
  const steps = screen.getAllByRole('button');
  expect(steps[1]).toHaveClass(/active|current|highlight/);
});

test('completed steps show checkmark', () => {
  render(<StepIndicator currentStep={3} completedSteps={new Set([1, 2])} />);
  // Steps 1-2 should have check indicators
  const steps = screen.getAllByRole('button');
  expect(steps[0]).toHaveAttribute('data-completed', 'true');
  expect(steps[1]).toHaveAttribute('data-completed', 'true');
});

test('future steps are disabled', () => {
  render(<StepIndicator currentStep={1} completedSteps={new Set()} />);
  const steps = screen.getAllByRole('button');
  expect(steps[1]).toBeDisabled();
  expect(steps[2]).toBeDisabled();
  expect(steps[3]).toBeDisabled();
});
```

运行:
```bash
cd dashboard && npm test -- --testPathPattern="StepIndicator" --watch=false
# 必须 FAIL — 组件不存在
```

### 🟢 GREEN

**新建**: `dashboard/src/components/generation/StepIndicator.tsx`

```tsx
import { Check, Circle } from 'lucide-react';

interface Props {
  currentStep: number;
  completedSteps: Set<number>;
}

const STEPS = [
  { num: 1, label: '场景' },
  { num: 2, label: '角色' },
  { num: 3, label: '背景' },
  { num: 4, label: '脚本' },
];

export function StepIndicator({ currentStep, completedSteps }: Props) {
  return (
    <div className="flex items-center gap-2" role="navigation">
      {STEPS.map(({ num, label }, i) => {
        const isCompleted = completedSteps.has(num);
        const isCurrent = num === currentStep;
        const isFuture = num > currentStep;

        return (
          <div key={num} className="flex items-center gap-2">
            <button
              role="button"
              disabled={isFuture}
              data-completed={isCompleted}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium transition-colors
                ${isCompleted ? 'bg-green-100 text-green-700' : ''}
                ${isCurrent ? 'bg-blue-100 text-blue-700 ring-2 ring-blue-500' : ''}
                ${isFuture ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : ''}
              `}
            >
              {isCompleted ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}
              {label}
            </button>
            {i < 3 && <span className="text-gray-300">→</span>}
          </div>
        );
      })}
    </div>
  );
}
```

### ✅ 验证

```bash
cd dashboard && npm test -- --testPathPattern="StepIndicator" --watch=false  # 4 PASS
```

---

## Step B2: 场景大纲审阅组件 (步骤 1)

### 🔴 RED — 前端测试

**新建**: `dashboard/src/components/generation/__tests__/Step1SceneOutline.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import { Step1SceneOutline } from '../Step1SceneOutline';

const mockData = {
  chapters: [
    {
      chapter_id: 'ch1',
      chapter_name: 'The Gathering Storm',
      chapter_order: 1,
      scenes: [
        { scene_id: 'ch1-s1', title: '余烬守望', summary: 'test', location: '废墟', mood: '悲壮', characters_present: ['Aldric'], dialogue_beats: [] },
        { scene_id: 'ch1-s2', title: '银发预言', summary: 'test', location: '神殿', mood: '神秘', characters_present: ['Seraphina'], dialogue_beats: [] },
      ],
    },
  ],
};

test('renders chapter names and scene counts', () => {
  render(<Step1SceneOutline data={mockData} onConfirm={jest.fn()} />);
  expect(screen.getByText('The Gathering Storm')).toBeInTheDocument();
  expect(screen.getByText('2 个场景')).toBeInTheDocument();
});

test('shows scene details when a scene is clicked', () => {
  render(<Step1SceneOutline data={mockData} onConfirm={jest.fn()} />);
  fireEvent.click(screen.getByText('余烬守望'));
  expect(screen.getByText('废墟')).toBeInTheDocument();
  expect(screen.getByText('悲壮')).toBeInTheDocument();
});

test('confirm button is visible', () => {
  render(<Step1SceneOutline data={mockData} onConfirm={jest.fn()} />);
  expect(screen.getByRole('button', { name: /确认场景大纲/ })).toBeInTheDocument();
});

test('confirm button calls onConfirm', () => {
  const onConfirm = jest.fn();
  render(<Step1SceneOutline data={mockData} onConfirm={onConfirm} />);
  fireEvent.click(screen.getByRole('button', { name: /确认场景大纲/ }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
});
```

### 🟢 GREEN

**新建**: `dashboard/src/components/generation/Step1SceneOutline.tsx`

组件结构参考 `GenerationWorkspace` 设计文档的步骤 1 布局——左侧章节场景列表 + 右侧场景详情。场景数据来自已有的 `GET /api/projects/:name/scenes` API。

### ✅ 验证

```bash
cd dashboard && npm test -- --testPathPattern="Step1SceneOutline" --watch=false  # 4 PASS
```

---

## Step B3: GenerationWorkspace 页面组装

### 🟢 — 组装（无新测试，组件已有测试覆盖）

**新建**: `dashboard/src/pages/GenerationWorkspacePage.tsx`

- 路由: `/dashboard/projects/:name/generate`
- 读取 URL param `name`，调用 `/api/projects/:name/scenes` 获取场景数据
- 根据 `generation_state.currentStep` 渲染对应步骤组件
- WebSocket 连接 `/ws/chat`，监听 `generation_step` 消息控制步骤切换

**修改**: `dashboard/src/App.tsx` — 新增路由

```tsx
<Route path="/projects/:name/generate" element={<GenerationWorkspacePage />} />
```

**修改**: `ProjectWorkspacePage.tsx` — post-freeze status 出现时，显示"进入分步生成"按钮，链接到 `/dashboard/projects/:name/generate`

### ✅ 验证

```bash
cd dashboard && npm run build  # 构建成功，无 TS 错误
```

---

# Part C: 全量回归

```bash
# 后端
python -m pytest tests/unit/ tests/integration/ --tb=line -q 2>&1 | grep -E "passed|failed"

# 前端
cd dashboard && npm test -- --watch=false

# E2E
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -v --tb=short -s
```

---

## 禁止事项

- ❌ 不要删除现有的一次性生成路径 — 保留为回退（`RENPY_MCP_LEGACY_GENERATION=1` 环境变量控制）
- ❌ 不要修改 `prototype_generation_service.py` 的核心生成逻辑 — 只加 WS 消息发送点
- ❌ 不要在 Part B 写 Part A 的代码，反之亦然
- ❌ 不要引入新的 npm 依赖

## 常见问题

**Q: `GenerationStepController` 应该放在哪个文件？**
A: `src/renpy_mcp/services/prototype_orchestration.py`，与 `PrototypeOrchestrationService` 同文件。

**Q: 前端如何获取初始的 scene 数据？**
A: 调用已有的 `GET /api/projects/:name/scenes` API（已有 endpoint）。

**Q: 角色/背景的图片 URL 格式？**
A: 沿用已有格式——`/api/projects/:name/assets/:relative_path`。

**Q: 前端测试 `fireEvent` 需要从哪里导入？**
A: `import { render, screen, fireEvent } from '@testing-library/react'`

**Q: 构建失败？**
A: 报告给我，列出具体的 TS 错误。

---

## 完成后输出

```
=== 分步生成 TDD 执行报告 ===

## Part A: 后端
- A1 (步骤控制器): RED X fail, GREEN X pass
- A2 (WS 消息): RED X fail, GREEN X pass
- A3 (集成): X/X pass

## Part B: 前端
- B1 (StepIndicator): RED X fail, GREEN X pass
- B2 (Step1SceneOutline): RED X fail, GREEN X pass
- B3 (GenerationWorkspace): 构建 OK

## Part C: 回归
- 后端: X/X pass
- 前端测试: X/X pass
- E2E: PASS/FAIL

## 遇到的问题
```
