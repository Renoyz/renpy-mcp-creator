import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { IntakeWorkspaceView } from "./IntakeWorkspaceView"

function createChapterIntake(outlineReady: boolean) {
  return {
    phase: outlineReady ? "outline_ready" : "chapter",
    current_summary: "Brief confirmed. Collecting chapter details.",
    missing_slots: [],
    slots: {},
    brief_draft_ready: true,
    chapter_draft: [
      {
        chapter_id: "ch1",
        order: 1,
        chapter_name: "Departure",
        chapter_goal: "Establish motivation",
        key_conflict: "Elena vs authority",
        emotional_arc: "hope -> tension",
        reveals: "Brother is missing",
        end_state: "Elena leaves home",
        mood_or_pacing_bias: "slow",
        character_focus: ["elena"],
        relationship_shift: "Elena distances from parents",
        character_presentation_notes: "Civilian clothes",
      },
    ],
    outline_draft_ready: outlineReady,
    updated_at: "",
  }
}

describe("IntakeWorkspaceView outline progress", () => {
  it("shows outline generation progress while chapter intake is still in progress", () => {
    render(
      <IntakeWorkspaceView
        intake={createChapterIntake(false)}
        projectName="test"
        onPromoteBriefDraft={vi.fn()}
        onPromoteOutlineDraft={vi.fn()}
      />
    )

    expect(screen.getByText(/preparing outline review/i)).toBeInTheDocument()
    expect(screen.getByTestId("outline-phase-progress")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /enter outline review/i })
    ).not.toBeInTheDocument()
  })

  it("shows enter outline review when the outline draft is ready", () => {
    render(
      <IntakeWorkspaceView
        intake={createChapterIntake(true)}
        projectName="test"
        onPromoteBriefDraft={vi.fn()}
        onPromoteOutlineDraft={vi.fn()}
      />
    )

    expect(screen.getByRole("button", { name: /enter outline review/i })).toBeInTheDocument()
  })
})
