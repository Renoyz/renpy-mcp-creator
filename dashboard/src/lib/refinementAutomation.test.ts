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
    expect(refresh).toHaveBeenCalledTimes(4)
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
    ).rejects.toThrow("场景包生成失败：LLM provider unavailable")
    expect(refresh).toHaveBeenCalledTimes(1)
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
    expect(refresh).toHaveBeenCalledTimes(5)
  })

  it("stops polling scene packages after the attempt cap and points at the Generation tab", async () => {
    const freezeBlueprint = vi.fn().mockResolvedValue(undefined)
    const refresh = vi.fn().mockResolvedValue(undefined)
    const request = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        complete: false,
        scene_generation: { status: "in_progress", completed_count: 0, total_count: 1 },
      }),
    })

    await expect(
      runFreezeAutoGenerationChain({
        projectName: "demo",
        freezeBlueprint,
        refreshProjectData: refresh,
        request,
      })
    ).rejects.toThrow(/生成”页继续/)

    // total_count = 1 -> attempt cap = max(12, 1 * 3) = 12 scene-package calls, then it stops
    expect(request).toHaveBeenCalledTimes(12)
    expect(
      request.mock.calls.every(([url]) => String(url).includes("/scene-packages/generate"))
    ).toBe(true)
  })

  it("stops polling scene packages when the wall-clock cap is exceeded", async () => {
    const freezeBlueprint = vi.fn().mockResolvedValue(undefined)
    const refresh = vi.fn().mockResolvedValue(undefined)
    let now = 1_000_000
    const nowSpy = vi.spyOn(Date, "now").mockImplementation(() => now)
    try {
      const request = vi.fn().mockImplementation(async () => {
        now += 5 * 60 * 1000 // each backend response arrives 5 minutes later
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            complete: false,
            scene_generation: { status: "in_progress", completed_count: 3, total_count: 100 },
          }),
        }
      })

      await expect(
        runFreezeAutoGenerationChain({
          projectName: "demo",
          freezeBlueprint,
          refreshProjectData: refresh,
          request,
        })
      ).rejects.toThrow(/生成”页继续/)

      // attempt cap would be 300 for 100 chapters; the wall clock must stop it much earlier
      expect(request.mock.calls.length).toBeLessThan(10)
    } finally {
      nowSpy.mockRestore()
    }
  })
})

