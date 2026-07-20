import { describe, it, expect, vi, afterEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { ProjectSelectPage } from "./ProjectSelectPage"

vi.mock("@/context/ProjectContext", () => ({
  useProject: vi.fn(),
}))

import { useProject } from "@/context/ProjectContext"

describe("ProjectSelectPage create dialog", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.mocked(useProject).mockReset()
  })

  it("shows an inline error instead of alert when project creation fails", async () => {
    const user = userEvent.setup()
    const alertSpy = vi.fn()
    vi.stubGlobal("alert", alertSpy)
    vi.mocked(useProject).mockReturnValue({ selectProject: vi.fn() } as never)

    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return { ok: false, status: 500, json: async () => ({}) }
      }
      return { ok: true, json: async () => ({ projects: [], errors: [] }) }
    })
    vi.stubGlobal("fetch", fetchMock)

    render(
      <MemoryRouter>
        <ProjectSelectPage />
      </MemoryRouter>
    )

    await user.click(await screen.findByTestId("new-project-cta"))
    await user.type(screen.getByTestId("create-project-name-input"), "demo")
    await user.click(screen.getByTestId("create-project-submit"))

    expect(await screen.findByTestId("create-project-error")).toHaveTextContent("创建项目失败")
    expect(alertSpy).not.toHaveBeenCalled()
    // Dialog stays open so the user can fix the name and retry.
    expect(screen.getByTestId("create-project-dialog")).toBeInTheDocument()
  })

  it("clears the inline error when the dialog is reopened", async () => {
    const user = userEvent.setup()
    vi.stubGlobal("alert", vi.fn())
    vi.mocked(useProject).mockReturnValue({ selectProject: vi.fn() } as never)

    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return { ok: false, status: 500, json: async () => ({}) }
      }
      return { ok: true, json: async () => ({ projects: [], errors: [] }) }
    })
    vi.stubGlobal("fetch", fetchMock)

    render(
      <MemoryRouter>
        <ProjectSelectPage />
      </MemoryRouter>
    )

    await user.click(await screen.findByTestId("new-project-cta"))
    await user.type(screen.getByTestId("create-project-name-input"), "demo")
    await user.click(screen.getByTestId("create-project-submit"))
    await screen.findByTestId("create-project-error")

    await user.click(screen.getByRole("button", { name: "取消" }))
    await user.click(screen.getByTestId("new-project-cta"))

    expect(screen.queryByTestId("create-project-error")).not.toBeInTheDocument()
  })
})
