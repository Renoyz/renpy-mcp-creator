import { describe, it, expect } from "vitest"
import type { GenerationState, RefinementStatus } from "@/context/ProjectContext"
import { deriveWorkflowDashboardState } from "./workflowState"

const frozenStatus: RefinementStatus = {
  refinement_state: "blueprint_ready",
  brief_fully_confirmed: true,
  outline_fully_confirmed: true,
  blueprint_ready: true,
  freeze_allowed: false,
  blueprint_freeze_status: "frozen",
  generation_allowed: true,
}

function generationStateAt(state: GenerationState["state"]): GenerationState {
  return {
    state,
    round_id: "r1",
    scene_generation: {
      status: "complete",
      current_chapter_id: null,
      completed_count: 1,
      total_count: 1,
      chapters: [],
    },
    character_assets: {},
    background_assets: {},
    script_preview: null,
  }
}

function deriveWith(state: GenerationState["state"]) {
  return deriveWorkflowDashboardState({
    hasBrief: true,
    hasBlueprint: true,
    refinementStatus: frozenStatus,
    refinementIntake: null,
    generationState: generationStateAt(state),
    buildStatus: "idle",
    previewAvailable: false,
    previewUrl: null,
    postFreezeRunning: false,
  })
}

describe("deriveWorkflowDashboardState generation gating", () => {
  it("points the primary action at character generation instead of build when scene packages are done but asset steps are incomplete", () => {
    // Exact state after the freeze auto-chain completes: genState "idle",
    // scene packages complete, no build/preview yet. Previously this fell
    // through to the hasBlueprint branch and offered a "构建" CTA.
    const state = deriveWith("idle")

    expect(state.primaryAction.action).toBe("open_generation")
    expect(state.primaryAction.action).not.toBe("build_web")
    expect(state.title).not.toBe("下一步：构建")

    const characters = state.stages.find((stage) => stage.id === "characters")
    const script = state.stages.find((stage) => stage.id === "script")
    expect(characters?.status).toBe("ready")
    expect(script?.status).toBe("locked")
  })

  it("points at backgrounds when only characters are confirmed", () => {
    const state = deriveWith("character_assets_confirmed")

    expect(state.primaryAction.action).toBe("open_generation")
    expect(state.title).toBe("生成场景背景")
  })

  it("points at script generation when assets are confirmed but the script is not committed", () => {
    const state = deriveWith("background_assets_confirmed")

    expect(state.primaryAction.action).toBe("open_generation")
    expect(state.primaryAction.label).toBe("生成预览脚本")
  })

  it("points at script review when a script preview is waiting", () => {
    const state = deriveWith("script_preview")

    expect(state.primaryAction.action).toBe("open_generation")
    expect(state.status).toBe("needs_review")
  })

  it("still offers the build action once the script is committed", () => {
    const state = deriveWith("committed")

    expect(state.primaryAction.action).toBe("build_web")
    expect(state.primaryAction.label).toBe("构建 Web 预览")
  })
})
