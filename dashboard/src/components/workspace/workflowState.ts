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
      label: "Intake",
      status: hasBrief || refinementIntake?.brief_draft_ready ? "done" : "ready",
      detail: hasBrief ? "Project inputs collected" : "Collect project direction",
    },
    {
      id: "brief",
      label: "Brief",
      status: refinementStatus?.brief_fully_confirmed ? "done" : refinementIntake?.brief_draft_ready ? "needs_review" : "locked",
      detail: refinementStatus?.brief_fully_confirmed ? "Brief confirmed" : "Review project requirements",
    },
    {
      id: "outline",
      label: "Outline",
      status: refinementStatus?.outline_fully_confirmed ? "done" : refinementIntake?.outline_draft_ready ? "needs_review" : "locked",
      detail: refinementStatus?.outline_fully_confirmed ? "Chapter outline confirmed" : "Confirm chapter arc",
    },
    {
      id: "blueprint",
      label: "Blueprint",
      status: frozen ? "done" : refinementStatus?.freeze_allowed ? "needs_review" : hasBlueprint ? "ready" : "locked",
      detail: frozen ? "Blueprint frozen" : "Freeze the generation contract",
    },
    {
      id: "scene_packages",
      label: "Scene Packages",
      status: scenePackagesDone ? "done" : scenePackagesRunning ? "running" : frozen ? "ready" : "locked",
      detail: scenePackagesDone ? "Scene packages ready" : "Derive scenes from the frozen blueprint",
    },
    {
      id: "characters",
      label: "Characters",
      status: isAtOrAfterGeneration(genState, "character_assets_confirmed")
        ? "done"
        : genState === "character_assets_draft"
        ? "needs_review"
        : scenePackagesDone
        ? "ready"
        : "locked",
      detail: "Generate and accept character sprites",
    },
    {
      id: "backgrounds",
      label: "Backgrounds",
      status: isAtOrAfterGeneration(genState, "background_assets_confirmed")
        ? "done"
        : genState === "background_assets_draft"
        ? "needs_review"
        : isAtOrAfterGeneration(genState, "character_assets_confirmed")
        ? "ready"
        : "locked",
      detail: "Generate scene backgrounds",
    },
    {
      id: "script",
      label: "Script",
      status: genState === "committed" ? "done" : genState === "script_preview" ? "needs_review" : "locked",
      detail: "Preview and commit generated script",
    },
    {
      id: "build",
      label: "Build",
      status: buildStatus === "failed" ? "failed" : buildStatus === "running" ? "running" : buildStatus === "success" ? "done" : hasBlueprint ? "ready" : "locked",
      detail: "Build playable output",
    },
    {
      id: "preview",
      label: "Preview",
      status: previewUrl ? "done" : previewAvailable ? "ready" : "locked",
      detail: "Launch the playable web preview",
    },
  ]

  let activeId = "intake"
  let title = "Project intake"
  let subtitle = "Start by collecting enough project direction for the agent to draft a brief."
  let status: WorkflowStageStatus = "ready"
  let primaryAction: WorkflowDashboardState["primaryAction"] = { label: "Start Intake", action: "open_intake" }

  if (refinementIntake?.brief_draft_ready && !hasBrief) {
    activeId = "brief"
    title = "Brief review is ready"
    subtitle = "The agent has enough intake material. Review the Project Brief before chapter planning."
    status = "needs_review"
    primaryAction = { label: "Enter Brief Review", action: "promote_brief" }
  } else if (refinementIntake?.outline_draft_ready && !refinementStatus?.outline_fully_confirmed) {
    activeId = "outline"
    title = "Outline review is ready"
    subtitle = "Chapter-level planning is ready for review and confirmation."
    status = "needs_review"
    primaryAction = { label: "Enter Outline Review", action: "promote_outline" }
  } else if (refinementStatus?.freeze_allowed && !frozen) {
    activeId = "blueprint"
    title = "Blueprint freeze"
    subtitle = "The confirmed brief and outline can now be frozen into the generation contract."
    status = "needs_review"
    primaryAction = { label: "Freeze Blueprint", action: "freeze" }
  } else if (scenePackagesRunning) {
    activeId = "scene_packages"
    title = "Generating scene packages"
    subtitle = "The system is deriving playable scene material from the frozen blueprint."
    status = "running"
    primaryAction = { label: "Open Generation", action: "open_generation" }
  } else if (frozen && !scenePackagesDone) {
    activeId = "scene_packages"
    title = "Scene packages ready"
    subtitle = "Move into generation to derive scene packages, assets, scripts, and preview output."
    status = "ready"
    primaryAction = { label: "Generate Scene Packages", action: "open_generation" }
  } else if (genState === "character_assets_draft") {
    activeId = "characters"
    title = "Character assets need review"
    subtitle = "Review generated character sprites and accept the renderable candidates."
    status = "needs_review"
    primaryAction = { label: "Review Character Assets", action: "open_generation" }
  } else if (genState === "background_assets_draft") {
    activeId = "backgrounds"
    title = "Scene backgrounds need review"
    subtitle = "Review generated backgrounds and accept the images that are safe to render."
    status = "needs_review"
    primaryAction = { label: "Review Backgrounds", action: "open_generation" }
  } else if (buildStatus === "failed") {
    activeId = "build"
    title = "Build failed"
    subtitle = "The last build did not complete. Retry after reviewing the build message below."
    status = "failed"
    primaryAction = { label: "Retry Web Build", action: "build_web" }
  } else if (previewAvailable || previewUrl) {
    activeId = "preview"
    title = "Preview ready"
    subtitle = "A playable web build is available for review."
    status = "ready"
    primaryAction = { label: "Open Preview", action: "preview" }
  } else if (hasBlueprint) {
    activeId = "build"
    title = "Build next"
    subtitle = "The project has generated material. Build a web preview to start playtesting."
    status = "ready"
    primaryAction = { label: "Build Web Preview", action: "build_web" }
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

