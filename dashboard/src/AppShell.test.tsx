import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AppShell } from "./AppShell"

vi.mock("./components/ChatDrawer", () => ({
  ChatDrawer: ({ mode }: { mode?: string }) => (
    <div data-testid={mode === "docked" ? "chat-panel-docked" : "chat-drawer"} />
  ),
}))

function renderWorkspaceShell() {
  return render(
    <MemoryRouter initialEntries={["/projects/demo"]}>
      <AppShell>
        <div>Workspace content</div>
      </AppShell>
    </MemoryRouter>
  )
}

describe("AppShell workspace AI dock", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true })
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(min-width: 1024px)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  })

  it("collapses and restores the desktop AI assistant panel", async () => {
    const user = userEvent.setup()
    renderWorkspaceShell()

    expect(screen.getByTestId("workspace-chat-dock")).toHaveClass("w-[320px]")
    expect(screen.getByTestId("chat-panel-docked")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Collapse AI assistant" }))

    expect(screen.getByTestId("workspace-chat-dock")).toHaveClass("w-12")
    expect(screen.queryByTestId("chat-panel-docked")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Expand AI assistant" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Expand AI assistant" }))

    expect(screen.getByTestId("workspace-chat-dock")).toHaveClass("w-[320px]")
    expect(screen.getByTestId("chat-panel-docked")).toBeInTheDocument()
  })
})
