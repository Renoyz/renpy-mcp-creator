import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { WorkspaceTabs } from "./WorkspaceTabs"

describe("WorkspaceTabs", () => {
  it("should render Game Shell tab and switch when clicked", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <WorkspaceTabs
        activeTab="intake"
        onChange={onChange}
        hasSceneSelected={false}
      />
    )

    const gameShellTab = screen.getByRole("button", { name: "Game Shell" })
    expect(gameShellTab).toBeInTheDocument()

    await user.click(gameShellTab)
    expect(onChange).toHaveBeenCalledWith("gameshell")
  })
})
