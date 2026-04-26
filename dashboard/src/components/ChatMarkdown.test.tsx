import "@testing-library/jest-dom/vitest"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ChatMarkdown } from "./ChatMarkdown"

describe("ChatMarkdown", () => {
  it("renders bold text and unordered list markers in assistant messages", () => {
    render(
      <ChatMarkdown
        content={
          '**方案 C：「饲主」**\n- 核心母题：吸血鬼的"饲养"\n- 情感基调：危险、诱惑'
        }
      />
    )

    expect(screen.getByText("方案 C：「饲主」")).toBeInTheDocument()
    expect(screen.getByText("方案 C：「饲主」").tagName).toBe("STRONG")
    expect(screen.getByText(/核心母题/).tagName).toBe("LI")
    expect(screen.getByText(/情感基调/).tagName).toBe("LI")
    expect(screen.queryByText(/\*\*方案 C/)).not.toBeInTheDocument()
  })
})
