import { describe, expect, it, vi } from "vitest"
import { runFreezeAutoGenerationChain } from "./refinementAutomation"

describe("runFreezeAutoGenerationChain", () => {
  it("runs freeze, scene package generation, prototype generation, and activation in order", async () => {
    const freezeBlueprint = vi.fn().mockResolvedValue(undefined)
    const refresh = vi.fn().mockResolvedValue(undefined)
    const events: string[] = []
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ success: true, chapters: [{ chapter_id: "ch1", scene_count: 2 }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ success: true, chapters_generated: ["ch1"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ success: true, mode: "multi_chapter" }),
      })

    await runFreezeAutoGenerationChain({
      projectName: "demo",
      freezeBlueprint,
      refreshProjectData: refresh,
      request,
      onProgress: (event) => events.push(`${event.status}:${event.step}`),
    })

    expect(freezeBlueprint).toHaveBeenCalledWith("demo")
    expect(request).toHaveBeenNthCalledWith(1, "/api/projects/demo/scene-packages/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(request).toHaveBeenNthCalledWith(2, "/api/projects/demo/prototype/multi-chapter/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(request).toHaveBeenNthCalledWith(3, "/api/projects/demo/prototype/multi-chapter/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(refresh).toHaveBeenCalledTimes(3)
    expect(events).toEqual([
      "running:freezing",
      "running:scene_packages",
      "running:prototype",
      "running:activating",
      "success:complete",
    ])
  })

  it("surfaces the backend detail when scene package generation fails", async () => {
    const freezeBlueprint = vi.fn().mockResolvedValue(undefined)
    const refresh = vi.fn().mockResolvedValue(undefined)
    const request = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "LLM provider unavailable" }),
    })

    await expect(
      runFreezeAutoGenerationChain({
        projectName: "demo",
        freezeBlueprint,
        refreshProjectData: refresh,
        request,
      })
    ).rejects.toThrow("Scene package generation failed: LLM provider unavailable")
  })

  it("keeps advancing scene packages until every chapter is complete", async () => {
    const freezeBlueprint = vi.fn().mockResolvedValue(undefined)
    const refresh = vi.fn().mockResolvedValue(undefined)
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          complete: false,
          scene_generation: { status: "in_progress", completed_count: 1, total_count: 2 },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          complete: true,
          scene_generation: { status: "complete", completed_count: 2, total_count: 2 },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ success: true, chapters_generated: ["ch1", "ch2"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ success: true, mode: "multi_chapter" }),
      })

    await runFreezeAutoGenerationChain({
      projectName: "demo",
      freezeBlueprint,
      refreshProjectData: refresh,
      request,
    })

    expect(request).toHaveBeenNthCalledWith(1, "/api/projects/demo/scene-packages/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(request).toHaveBeenNthCalledWith(2, "/api/projects/demo/scene-packages/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(request).toHaveBeenNthCalledWith(3, "/api/projects/demo/prototype/multi-chapter/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    expect(refresh).toHaveBeenCalledTimes(4)
  })
})

