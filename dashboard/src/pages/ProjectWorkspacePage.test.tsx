import { describe, it, expect, vi, afterEach } from "vitest"
import { render, screen, within } from "@testing-library/react"
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

    const webButton = await screen.findByRole("button", { name: "Primary action: Build Web Preview" })
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
    expect(screen.getByRole("button", { name: "Primary action: Open Preview" })).toBeEnabled()
  })

  it("shows a workflow header with brief review as the primary action when intake is ready", async () => {
    const user = userEvent.setup()
    const promoteBriefDraft = vi.fn().mockResolvedValue(undefined)
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      blueprint: null,
      brief: null,
      refinementIntake: {
        phase: "project",
        current_summary: "The detective premise is ready for review.",
        missing_slots: [],
        slots: {},
        brief_draft_ready: true,
        chapter_draft: [],
        outline_draft_ready: false,
        updated_at: "2026-04-27T00:00:00",
      },
      refinementStatus: {
        refinement_state: "intake_ready",
        brief_fully_confirmed: false,
        outline_fully_confirmed: false,
        blueprint_ready: false,
        freeze_allowed: false,
        blueprint_freeze_status: null,
        generation_allowed: false,
      },
      promoteBriefDraft,
    } as never)

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const header = await screen.findByTestId("workflow-status-header")
    expect(header).toHaveTextContent("Step")
    expect(header).toHaveTextContent("Brief review is ready")

    await user.click(within(header).getByRole("button", { name: "Primary action: Enter Brief Review" }))

    expect(promoteBriefDraft).toHaveBeenCalledWith("demo")
  })

  it("keeps refinement blockers inside the compact workflow header", async () => {
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      blueprint: null,
      refinementIntake: {
        phase: "project",
        current_summary: "The agent is still collecting project requirements.",
        missing_slots: ["core_premise"],
        slots: {
          core_premise: { value: null, complete: false },
        },
        brief_draft_ready: false,
        chapter_draft: [],
        outline_draft_ready: false,
        updated_at: "2026-04-27T00:00:00",
      },
      refinementStatus: {
        refinement_state: "intake",
        brief_fully_confirmed: false,
        outline_fully_confirmed: false,
        blueprint_ready: false,
        freeze_allowed: false,
        blueprint_freeze_status: null,
        generation_allowed: false,
      },
    } as never)

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const header = await screen.findByTestId("workflow-status-header")
    const blocker = within(header).getByTestId("workflow-blocker-chip")
    expect(blocker).toHaveTextContent("Complete all Project Brief cards first")
    expect(screen.queryByTestId("refinement-status-panel")).not.toBeInTheDocument()
  })

  it("shows freeze blueprint as the primary action when the outline is confirmed", async () => {
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      brief: { cards: {}, updated_at: "2026-04-27T00:00:00" },
      chapterOutline: { chapters: [], updated_at: "2026-04-27T00:00:00" },
      refinementStatus: {
        refinement_state: "outline_confirmed",
        brief_fully_confirmed: true,
        outline_fully_confirmed: true,
        blueprint_ready: true,
        freeze_allowed: true,
        blueprint_freeze_status: "draft",
        generation_allowed: false,
      },
    } as never)

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const header = await screen.findByTestId("workflow-status-header")
    expect(header).toHaveTextContent("Blueprint freeze")
    expect(within(header).getByRole("button", { name: "Primary action: Freeze Blueprint" })).toBeInTheDocument()
  })

  it("renders a workflow rail with production stages and scene navigation", async () => {
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      chapters: [
        {
          id: "ch1",
          name: "Opening",
          order: 1,
          scenes: [
            { id: "s1", name: "First clue", order: 1, status: "generated" },
          ],
        },
      ],
      selectedSceneId: "s1",
      refinementStatus: {
        refinement_state: "blueprint_ready",
        brief_fully_confirmed: true,
        outline_fully_confirmed: true,
        blueprint_ready: true,
        freeze_allowed: false,
        blueprint_freeze_status: "frozen",
        generation_allowed: true,
      },
    } as never)

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const rail = await screen.findByTestId("workflow-rail")
    expect(rail).toHaveTextContent("Intake")
    expect(rail).toHaveTextContent("Brief")
    expect(rail).toHaveTextContent("Outline")
    expect(rail).toHaveTextContent("Scene Packages")
    expect(rail).toHaveTextContent("Build")
    expect(rail).toHaveTextContent("Preview")
    expect(rail).toHaveTextContent("First clue")
  })
})

describe("ProjectWorkspacePage brief promote flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.mocked(useProject).mockReset()
  })

  const briefReadyContext = {
    ...baseContext,
    blueprint: null,
    brief: null,
    refinementIntake: {
      phase: "project",
      current_summary: "The detective premise is ready for review.",
      missing_slots: [],
      slots: {},
      brief_draft_ready: true,
      chapter_draft: [],
      outline_draft_ready: false,
      updated_at: "2026-04-27T00:00:00",
    },
    refinementStatus: {
      refinement_state: "intake_ready",
      brief_fully_confirmed: false,
      outline_fully_confirmed: false,
      blueprint_ready: false,
      freeze_allowed: false,
      blueprint_freeze_status: null,
      generation_allowed: false,
    },
  }

  const stubStatusFetches = () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )
  }

  it("keeps the user on the intake tab and shows an inline error when brief promote fails", async () => {
    const user = userEvent.setup()
    const promoteBriefDraft = vi.fn().mockRejectedValue(new Error("Brief draft is not ready yet"))
    vi.mocked(useProject).mockReturnValue({
      ...briefReadyContext,
      refinementStatus: {
        ...briefReadyContext.refinementStatus,
        intake_required: true,
      },
      promoteBriefDraft,
    } as never)
    stubStatusFetches()

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const header = await screen.findByTestId("workflow-status-header")
    await user.click(within(header).getByRole("button", { name: "Primary action: Enter Brief Review" }))

    const status = await screen.findByTestId("brief-review-status")
    expect(status).toHaveTextContent("Brief draft is not ready yet")
    expect(screen.getByTestId("intake-progress-panel")).toBeInTheDocument()
    expect(screen.queryByText("Start in Intake first")).not.toBeInTheDocument()
  })

  it("switches to the brief tab with a success status only after brief promote succeeds", async () => {
    const user = userEvent.setup()
    const promoteBriefDraft = vi.fn().mockResolvedValue(undefined)
    vi.mocked(useProject).mockReturnValue({
      ...briefReadyContext,
      promoteBriefDraft,
    } as never)
    stubStatusFetches()

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    const header = await screen.findByTestId("workflow-status-header")
    await user.click(within(header).getByRole("button", { name: "Primary action: Enter Brief Review" }))

    const status = await screen.findByTestId("brief-review-status")
    expect(status).toHaveTextContent("Project Brief review is ready.")
    expect(screen.getByText("No Project Brief yet")).toBeInTheDocument()
  })
})

describe("ProjectWorkspacePage generation gating", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.mocked(useProject).mockReset()
  })

  const stubStatusFetches = () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ stage: "idle", previewable: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: "idle" }),
        })
    )
  }

  it("disables the generation tab start actions until the blueprint is frozen", async () => {
    const user = userEvent.setup()
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      brief: { cards: {}, updated_at: "2026-04-27T00:00:00" },
      chapterOutline: { chapters: [], updated_at: "2026-04-27T00:00:00" },
      refinementStatus: {
        refinement_state: "outline_confirmed",
        brief_fully_confirmed: true,
        outline_fully_confirmed: true,
        blueprint_ready: true,
        freeze_allowed: true,
        blueprint_freeze_status: "draft",
        generation_allowed: false,
      },
    } as never)
    stubStatusFetches()

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(await screen.findByRole("button", { name: "Generation" }))

    const blocked = await screen.findByTestId("generation-blocked-reason")
    expect(blocked).toHaveTextContent("Freeze the blueprint to unlock generation")
    expect(screen.getByRole("button", { name: "Start Characters" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Start Backgrounds" })).toBeDisabled()
  })

  it("enables the generation tab start actions when generation is allowed", async () => {
    const user = userEvent.setup()
    vi.mocked(useProject).mockReturnValue({
      ...baseContext,
      brief: { cards: {}, updated_at: "2026-04-27T00:00:00" },
      chapterOutline: { chapters: [], updated_at: "2026-04-27T00:00:00" },
      refinementStatus: {
        refinement_state: "blueprint_ready",
        brief_fully_confirmed: true,
        outline_fully_confirmed: true,
        blueprint_ready: true,
        freeze_allowed: false,
        blueprint_freeze_status: "frozen",
        generation_allowed: true,
      },
    } as never)
    stubStatusFetches()

    render(
      <MemoryRouter initialEntries={["/projects/demo"]}>
        <Routes>
          <Route path="/projects/:name" element={<ProjectWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(await screen.findByRole("button", { name: "Generation" }))

    await screen.findByRole("button", { name: "Start Characters" })
    expect(screen.queryByTestId("generation-blocked-reason")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Start Characters" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Start Backgrounds" })).toBeEnabled()
  })
})
