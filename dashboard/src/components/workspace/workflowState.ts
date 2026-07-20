import type { GenerationState, RefinementIntake, RefinementStatus } from "@/context/ProjectContext"

export type WorkflowStageStatus = "locked" | "ready" | "running" | "needs_review" | "done" | "failed"

export type WorkflowAction =
  | "open_intake"
  | "promote_brief"
  | "promote_outline"
  | "freeze"
  | "open_generation"
  | "build_web"
  | "preview"

export interface WorkflowStage {
  id: string
  label: string
  status: WorkflowStageStatus
  detail: string
}

export interface WorkflowDashboardState {
  title: string
  subtitle: string
  currentStep: number
  totalSteps: number
  progressPercent: number
  status: WorkflowStageStatus
  primaryAction: {
    label: string
    action: WorkflowAction
    disabled?: boolean
  }
  stages: WorkflowStage[]
}

interface Args {
  hasBrief: boolean
  hasBlueprint: boolean
  refinementStatus: RefinementStatus | null
  refinementIntake: RefinementIntake | null
  generationState: GenerationState | null
  buildStatus: "idle" | "running" | "success" | "failed"
  previewAvailable: boolean
  previewUrl: string | null
  postFreezeRunning: boolean
}

const orderedStageIds = [
  "intake",
  "brief",
  "outline",
  "blueprint",
  "scene_packages",
  "characters",
  "backgrounds",
  "script",
  "build",
  "preview",
]

function progress(stages: WorkflowStage[]) {
  const done = stages.filter((stage) => stage.status === "done").length
  return Math.round((done / stages.length) * 100)
}

function stepIndex(stages: WorkflowStage[], titleId: string) {
  const idx = stages.findIndex((stage) => stage.id === titleId)
  return idx >= 0 ? idx + 1 : 1
}

function isAtOrAfterGeneration(state: GenerationState["state"] | undefined, target: GenerationState["state"]) {
  const order: GenerationState["state"][] = [
    "idle",
    "scene_outline_draft",
    "scene_outline_confirmed",
    "character_assets_draft",
    "character_assets_confirmed",
    "background_assets_draft",
    "background_assets_confirmed",
    "script_preview",
    "committed",
  ]
  return order.indexOf(state ?? "idle") >= order.indexOf(target)
}

export function deriveWorkflowDashboardState({
  hasBrief,
  hasBlueprint,
  refinementStatus,
  refinementIntake,
  generationState,
  buildStatus,
  previewAvailable,
  previewUrl,
  postFreezeRunning,
}: Args): WorkflowDashboardState {
  const frozen = refinementStatus?.blueprint_freeze_status === "frozen"
  const genState = generationState?.state ?? "idle"
  const sceneGeneration = generationState?.scene_generation
  const scenePackagesRunning = sceneGeneration?.status === "in_progress" || postFreezeRunning
  const scenePackagesDone = sceneGeneration?.status === "complete" || isAtOrAfterGeneration(genState, "character_assets_draft")

  const stages: WorkflowStage[] = [
    {
      id: "intake",
      label: "需求采集",
      status: hasBrief || refinementIntake?.brief_draft_ready ? "done" : "ready",
      detail: hasBrief ? "项目信息已收集" : "收集项目方向",
    },
    {
      id: "brief",
      label: "项目简报",
      status: refinementStatus?.brief_fully_confirmed ? "done" : refinementIntake?.brief_draft_ready ? "needs_review" : "locked",
      detail: refinementStatus?.brief_fully_confirmed ? "项目简报已确认" : "确认项目需求",
    },
    {
      id: "outline",
      label: "章节大纲",
      status: refinementStatus?.outline_fully_confirmed ? "done" : refinementIntake?.outline_draft_ready ? "needs_review" : "locked",
      detail: refinementStatus?.outline_fully_confirmed ? "章节大纲已确认" : "确认章节叙事弧线",
    },
    {
      id: "blueprint",
      label: "蓝图",
      status: frozen ? "done" : refinementStatus?.freeze_allowed ? "needs_review" : hasBlueprint ? "ready" : "locked",
      detail: frozen ? "蓝图已冻结" : "冻结生成契约",
    },
    {
      id: "scene_packages",
      label: "场景包",
      status: scenePackagesDone ? "done" : scenePackagesRunning ? "running" : frozen ? "ready" : "locked",
      detail: scenePackagesDone ? "场景包已就绪" : "从冻结的蓝图派生场景",
    },
    {
      id: "characters",
      label: "角色",
      status: isAtOrAfterGeneration(genState, "character_assets_confirmed")
        ? "done"
        : genState === "character_assets_draft"
        ? "needs_review"
        : scenePackagesDone
        ? "ready"
        : "locked",
      detail: "生成并验收角色立绘",
    },
    {
      id: "backgrounds",
      label: "背景",
      status: isAtOrAfterGeneration(genState, "background_assets_confirmed")
        ? "done"
        : genState === "background_assets_draft"
        ? "needs_review"
        : isAtOrAfterGeneration(genState, "character_assets_confirmed")
        ? "ready"
        : "locked",
      detail: "生成场景背景",
    },
    {
      id: "script",
      label: "脚本",
      status: genState === "committed" ? "done" : genState === "script_preview" ? "needs_review" : "locked",
      detail: "预览并提交生成的脚本",
    },
    {
      id: "build",
      label: "构建",
      status: buildStatus === "failed" ? "failed" : buildStatus === "running" ? "running" : buildStatus === "success" ? "done" : hasBlueprint ? "ready" : "locked",
      detail: "构建可游玩的产物",
    },
    {
      id: "preview",
      label: "预览",
      status: previewUrl ? "done" : previewAvailable ? "ready" : "locked",
      detail: "启动可游玩的 Web 预览",
    },
  ]

  let activeId = "intake"
  let title = "项目需求采集"
  let subtitle = "先收集足够的项目方向，让 AI 助手起草项目简报。"
  let status: WorkflowStageStatus = "ready"
  let primaryAction: WorkflowDashboardState["primaryAction"] = { label: "开始需求采集", action: "open_intake" }

  if (refinementIntake?.brief_draft_ready && !hasBrief) {
    activeId = "brief"
    title = "项目简报待审阅"
    subtitle = "AI 助手已收集足够的项目信息。请在章节规划前审阅项目简报。"
    status = "needs_review"
    primaryAction = { label: "进入简报审阅", action: "promote_brief" }
  } else if (refinementIntake?.outline_draft_ready && !refinementStatus?.outline_fully_confirmed) {
    activeId = "outline"
    title = "章节大纲待审阅"
    subtitle = "章节级规划已就绪，可以进行审阅与确认。"
    status = "needs_review"
    primaryAction = { label: "进入大纲审阅", action: "promote_outline" }
  } else if (refinementStatus?.freeze_allowed && !frozen) {
    activeId = "blueprint"
    title = "冻结蓝图"
    subtitle = "已确认的简报与大纲现在可以冻结为生成契约。"
    status = "needs_review"
    primaryAction = { label: "冻结蓝图", action: "freeze" }
  } else if (scenePackagesRunning) {
    activeId = "scene_packages"
    title = "正在生成场景包"
    subtitle = "系统正在从冻结的蓝图派生可游玩的场景内容。"
    status = "running"
    primaryAction = { label: "打开生成面板", action: "open_generation" }
  } else if (frozen && !scenePackagesDone) {
    activeId = "scene_packages"
    title = "准备生成场景包"
    subtitle = "进入生成环节，派生场景包、素材、脚本与预览产物。"
    status = "ready"
    primaryAction = { label: "生成场景包", action: "open_generation" }
  } else if (genState === "character_assets_draft") {
    activeId = "characters"
    title = "角色素材待审阅"
    subtitle = "审阅生成的角色立绘，并验收可渲染的候选素材。"
    status = "needs_review"
    primaryAction = { label: "审阅角色素材", action: "open_generation" }
  } else if (genState === "background_assets_draft") {
    activeId = "backgrounds"
    title = "场景背景待审阅"
    subtitle = "审阅生成的背景，并验收可以安全渲染的图片。"
    status = "needs_review"
    primaryAction = { label: "审阅背景", action: "open_generation" }
  } else if (frozen && scenePackagesDone && genState !== "committed") {
    // Generation/asset steps are still incomplete: point at the earliest
    // one instead of falling through to the build CTA.
    if (!isAtOrAfterGeneration(genState, "character_assets_confirmed")) {
      activeId = "characters"
      title = "生成角色素材"
      subtitle = "场景包已就绪。请先生成并验收角色立绘，然后再构建。"
      status = "ready"
      primaryAction = { label: "生成角色素材", action: "open_generation" }
    } else if (!isAtOrAfterGeneration(genState, "background_assets_confirmed")) {
      activeId = "backgrounds"
      title = "生成场景背景"
      subtitle = "角色素材已验收。请生成并验收场景背景，然后再构建。"
      status = "ready"
      primaryAction = { label: "生成场景背景", action: "open_generation" }
    } else if (genState === "script_preview") {
      activeId = "script"
      title = "脚本待审阅"
      subtitle = "脚本预览已生成。请审阅并提交脚本，然后再构建。"
      status = "needs_review"
      primaryAction = { label: "审阅脚本", action: "open_generation" }
    } else {
      activeId = "script"
      title = "生成预览脚本"
      subtitle = "素材已验收。请生成并提交脚本，然后再构建。"
      status = "ready"
      primaryAction = { label: "生成预览脚本", action: "open_generation" }
    }
  } else if (buildStatus === "failed") {
    activeId = "build"
    title = "构建失败"
    subtitle = "上一次构建未完成。请查看下方构建信息后重试。"
    status = "failed"
    primaryAction = { label: "重试 Web 构建", action: "build_web" }
  } else if (previewAvailable || previewUrl) {
    activeId = "preview"
    title = "预览就绪"
    subtitle = "已有可游玩的 Web 构建产物可供体验。"
    status = "ready"
    primaryAction = { label: "打开预览", action: "preview" }
  } else if (hasBlueprint) {
    activeId = "build"
    title = "下一步：构建"
    subtitle = "项目已有生成的内容。构建 Web 预览即可开始试玩。"
    status = "ready"
    primaryAction = { label: "构建 Web 预览", action: "build_web" }
  }

  return {
    title,
    subtitle,
    currentStep: stepIndex(stages, activeId),
    totalSteps: orderedStageIds.length,
    progressPercent: progress(stages),
    status,
    primaryAction,
    stages,
  }
}

