import { describe, it, expect, vi, afterEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { GameShellWorkspaceView } from "./GameShellWorkspaceView"

const buildApiShell = () => ({
  title: "Default Title",
  subtitle: "A calm mystery",
  theme: "Neon Noir",
  main_menu_background: "/images/menu_bg.png",
  show_gallery: true,
  show_endings: false,
  show_replay: false,
  show_credits: true,
  gallery_items: [
    {
      id: "gallery_a",
      title: "Gallery A",
      image_path: "game/images/a.png",
      source: "background",
      unlock_mode: "always",
      persistent_key: "",
    },
    {
      id: "gallery_b",
      title: "Gallery B",
      image_path: "game/images/b.png",
      source: "sprite",
      unlock_mode: "persistent",
      persistent_key: "seen_gallery_b",
    },
  ],
  ending_items: [
    {
      id: "ending_a",
      title: "Ending A",
      description: "A quiet ending.",
      unlock_mode: "always",
      persistent_key: "",
    },
  ],
  credits: ["Lead Writer: Demo"],
})

describe("GameShellWorkspaceView", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("loads data from project-scoped Game Shell endpoint and renders fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => buildApiShell(),
      })
    )

    render(<GameShellWorkspaceView projectName="demo" />)

    expect(await screen.findByDisplayValue("Default Title")).toBeInTheDocument()
    expect(screen.getByDisplayValue("A calm mystery")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Neon Noir")).toBeInTheDocument()
    expect(screen.getByDisplayValue("/images/menu_bg.png")).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "Gallery title 1" })).toHaveValue("Gallery A")
    expect(screen.getByRole("textbox", { name: "Gallery image path 1" })).toHaveValue("game/images/a.png")
    expect(screen.getByRole("textbox", { name: "Ending title 1" })).toHaveValue("Ending A")
    expect(screen.getByRole("textbox", { name: "Ending description 1" })).toHaveValue("A quiet ending.")
    expect(screen.getByRole("textbox", { name: "Credits" })).toHaveValue("Lead Writer: Demo")
  })

  it("loads structured backend gallery and credit payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...buildApiShell(),
          gallery_items: [{ id: "bg_1", title: "Rain Street" }],
          ending_items: [{ id: "ending_1", title: "True Ending" }],
          credits: ["Writer: AI", "Editor: User"],
        }),
      })
    )

    render(<GameShellWorkspaceView projectName="demo" />)

    expect(await screen.findByRole("textbox", { name: "Gallery title 1" })).toHaveValue("Rain Street")
    expect(screen.getByRole("textbox", { name: "Ending title 1" })).toHaveValue("True Ending")
    expect(screen.getByRole("textbox", { name: "Credits" })).toHaveValue("Writer: AI\nEditor: User")
  })

  it("saves Game Shell config with PUT /game-shell", async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve({
          ok: true,
          json: async () => buildApiShell(),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => buildApiShell(),
      })
    })

    vi.stubGlobal("fetch", fetchMock)

    render(<GameShellWorkspaceView projectName="demo" />)

    const titleInput = await screen.findByDisplayValue("Default Title")
    await user.clear(titleInput)
    await user.type(titleInput, "Updated Title")
    await user.click(screen.getByRole("button", { name: "Save" }))

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/game-shell",
      expect.objectContaining({
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildApiShell(),
          title: "Updated Title",
        }),
      })
    )
  })

  it("posts derive and render-preview requests to project-scoped routes", async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/game-shell/derive")) {
        return Promise.resolve({
          ok: true,
          json: async () => buildApiShell(),
        })
      }
      if (url.endsWith("/game-shell/render-preview")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            script_files: ["game/__staging__/shell/zz_generated_shell.rpy"],
            preview: "screen main_menu():",
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => buildApiShell(),
      })
    })

    vi.stubGlobal("fetch", fetchMock)

    render(<GameShellWorkspaceView projectName="demo" />)

    const deriveButton = await screen.findByRole("button", { name: /derive from prototype/i })
    await user.click(deriveButton)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/game-shell/derive",
      expect.objectContaining({ method: "POST" })
    )

    const renderButton = await screen.findByRole("button", { name: /render shell preview/i })
    await user.click(renderButton)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/game-shell/render-preview",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildApiShell()),
      })
    )
    expect(screen.getByText(/Rendered files:/)).toBeInTheDocument()
    expect(screen.getByText(/zz_generated_shell\.rpy/)).toBeInTheDocument()
    expect(screen.getByText("screen main_menu():")).toBeInTheDocument()
  })
})
