import { describe, it, expect, vi, afterEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ProjectWorkspacePage } from "./ProjectWorkspacePage"

vi.mock("@/context/ProjectContext", () => ({
  useProject: vi.fn(),
}))

import { useProject } from "@/context/ProjectContext"

const baseContext = {
  currentProject: { name: "demo", path: "/tmp/demo" },
  meta: null,
  blueprint: {},
  chapters: [],
  storymap: null,
  selectedSceneId: null,
  selectedSceneScript: null,
  scriptError: null,
  error: null,
  blueprintPhase: "idle",
  blueprintDraft: null,
  blueprintConfirmationId: null,
  workflowConfirmation: null,
  interviewMessages: [],
  generationProgress: null,
  brief: null,
  chapterOutline: null,
  refinementStatus: null,
  refinementIntake: null,
  briefError: null,
  chapterOutlineError: null,
  refinementStatusError: null,
  refinementIntakeError: null,
  generationState: null,
  refresh: vi.fn(),
  selectProject: vi.fn(),
  loadProjectData: vi.fn().mockResolvedValue(undefined),
  loadGenerationState: vi.fn(),
  selectScene: vi.fn(),
  setBlueprintPhase: vi.fn(),
  startBlueprintCollection: vi.fn(),
  sendBlueprintConfirmation: vi.fn(),
  registerBlueprintConfirmationSender: vi.fn(),
  registerBlueprintStartSender: vi.fn(),
  handleBlueprintEvent: vi.fn(),
  loadBrief: vi.fn(),
  saveBrief: vi.fn(),
  confirmCard: vi.fn(),
  loadChapterOutline: vi.fn(),
  saveChapterOutline: vi.fn(),
  confirmChapter: vi.fn(),
  loadRefinementStatus: vi.fn(),
  loadRefinementIntake: vi.fn(),
  freezeBlueprint: vi.fn(),
  promoteBriefDraft: vi.fn(),
  promoteOutlineDraft: vi.fn(),
}

describe("ProjectWorkspacePage build controls", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.mocked(useProject).mockReset()
  })

  it("calls build API with web target when building web preview", async () => {
    const user = userEvent.setup()
    vi.mocked(useProject).mockReturnValue(baseContext as never)

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ stage: "idle", previewable: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "idle" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_active: false, is_buildable: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, output_path: "build/out" }),
      })

    vi.stubGlobal("fetch", fetchMock)

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const webButton = await screen.findByRole("button", { name: /build web preview/i })
    await user.click(webButton)

    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/demo/prototype/status")
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/projects/demo/build",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "web" }),
      })
    )
  })

  it("calls build API with windows target when building windows package", async () => {
    const user = userEvent.setup()
    vi.mocked(useProject).mockReturnValue(baseContext as never)

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ stage: "idle", previewable: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "idle" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_active: false, is_buildable: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, output_path: "build/out" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_active: false, is_buildable: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, output_path: "build/win" }),
      })

    vi.stubGlobal("fetch", fetchMock)

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const windowsButton = await screen.findByRole("button", { name: /build windows package/i })
    await user.click(windowsButton)

    expect(fetchMock.mock.calls[2][0]).toBe("/api/projects/demo/prototype/status")
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/projects/demo/build",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "windows" }),
      })
    )
  })

  it("uses prototype build endpoint for active prototype windows package and preserves existing web preview", async () => {
    const user = userEvent.setup()
    vi.mocked(useProject).mockReturnValue(baseContext as never)

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ stage: "prototype_preview_ready", previewable: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: "idle" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ is_active: true, is_buildable: true, mode: "single_chapter" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, output_path: "build/win", target: "windows" }),
      })

    vi.stubGlobal("fetch", fetchMock)

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const windowsButton = await screen.findByRole("button", { name: /build windows package/i })
    await user.click(windowsButton)

    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/projects/demo/prototype/build",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "windows" }),
      })
    )
    expect(screen.getByText("Preview available")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^preview$/i })).toBeEnabled()
  })
})
