import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { act, render, screen } from "@testing-library/react"
import { ChatDrawer } from "./ChatDrawer"

vi.mock("@/context/ProjectContext", () => ({
  useProject: vi.fn(),
}))

import { useProject } from "@/context/ProjectContext"

class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = FakeWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }

  serverOpen() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  serverClose() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }
}

const projectContext = {
  currentProject: null,
  blueprintPhase: "idle",
  blueprintDraft: null,
  blueprintConfirmationId: null,
  workflowConfirmation: null,
  generationProgress: null,
  handleBlueprintEvent: vi.fn(),
  sendBlueprintConfirmation: vi.fn(),
  registerBlueprintConfirmationSender: vi.fn(),
  registerBlueprintStartSender: vi.fn(),
}

describe("ChatDrawer websocket reconnect", () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.useFakeTimers()
    vi.stubGlobal("WebSocket", FakeWebSocket)
    Element.prototype.scrollIntoView = vi.fn()
    vi.mocked(useProject).mockReturnValue(projectContext as never)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.mocked(useProject).mockReset()
  })

  it("reconnects with exponential backoff after an unexpected close, up to 5 attempts", () => {
    render(<ChatDrawer open onClose={() => {}} wsUrl="ws://test/ws" />)
    expect(FakeWebSocket.instances).toHaveLength(1)

    const delays = [1000, 2000, 4000, 8000, 16000]
    delays.forEach((delay, index) => {
      act(() => {
        FakeWebSocket.instances[index].serverClose()
      })
      // Not before the full delay has elapsed.
      act(() => {
        vi.advanceTimersByTime(delay - 1)
      })
      expect(FakeWebSocket.instances).toHaveLength(index + 1)
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(FakeWebSocket.instances).toHaveLength(index + 2)
    })

    // All 5 reconnect attempts failed: give up instead of looping forever.
    act(() => {
      FakeWebSocket.instances[5].serverClose()
    })
    act(() => {
      vi.advanceTimersByTime(60000)
    })
    expect(FakeWebSocket.instances).toHaveLength(6)
  })

  it("shows a reconnecting hint after an unexpected close and hides it once reconnected", () => {
    render(<ChatDrawer open onClose={() => {}} wsUrl="ws://test/ws" />)

    act(() => {
      FakeWebSocket.instances[0].serverClose()
    })
    expect(screen.getByText("连接已断开，正在重连…")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    act(() => {
      FakeWebSocket.instances[1].serverOpen()
    })
    expect(screen.queryByText("连接已断开，正在重连…")).not.toBeInTheDocument()
  })

  it("does not reconnect when the drawer is closed by the user", () => {
    const { rerender } = render(<ChatDrawer open onClose={() => {}} wsUrl="ws://test/ws" />)
    expect(FakeWebSocket.instances).toHaveLength(1)

    rerender(<ChatDrawer open={false} onClose={() => {}} wsUrl="ws://test/ws" />)

    act(() => {
      vi.advanceTimersByTime(60000)
    })
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(screen.queryByText("连接已断开，正在重连…")).not.toBeInTheDocument()
  })

  it("does not reconnect after unmount", () => {
    const { unmount } = render(<ChatDrawer open onClose={() => {}} wsUrl="ws://test/ws" />)
    expect(FakeWebSocket.instances).toHaveLength(1)

    unmount()

    act(() => {
      vi.advanceTimersByTime(60000)
    })
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
