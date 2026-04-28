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
  it("summarizes project intake as a visible collection workflow", () => {
    render(
      <IntakeWorkspaceView
        intake={{
          phase: "project",
          current_summary: "A mystery visual novel about a detective academy.",
          missing_slots: [
            "tone_themes",
            "visual_style",
            "world_rules",
            "core_cast",
            "character_identity",
            "relationship_baselines",
            "constraints",
          ],
          slots: {
            core_premise: { value: "Detective academy mystery", complete: true },
            audience_genre: { value: "YA mystery", complete: true },
            tone_themes: { value: null, complete: false },
            visual_style: { value: null, complete: false },
            world_rules: { value: null, complete: false },
            core_cast: { value: null, complete: false },
            character_identity: { value: null, complete: false },
            relationship_baselines: { value: null, complete: false },
            constraints: { value: null, complete: false },
          },
          brief_draft_ready: false,
          chapter_draft: [],
          outline_draft_ready: false,
          updated_at: "",
        }}
        projectName="test"
        onPromoteBriefDraft={vi.fn()}
        onPromoteOutlineDraft={vi.fn()}
      />
    )

    const progress = screen.getByTestId("intake-progress-panel")
    expect(progress).toHaveTextContent("Project intake progress")
    expect(progress).toHaveTextContent("2 / 9 slots collected")
    expect(progress).toHaveTextContent("7 remaining")
    expect(progress).toHaveTextContent("Next: keep chatting with AI")

    const requirements = screen.getByTestId("intake-requirements-grid")
    expect(requirements).toHaveTextContent("Requirements")
    expect(requirements).toHaveTextContent("Core Premise")
    expect(requirements).toHaveTextContent("Complete")
    expect(requirements).toHaveTextContent("Missing")
  })

  it("moves project intake to brief review when all required slots are collected", () => {
    render(
      <IntakeWorkspaceView
        intake={{
          phase: "project",
          current_summary: "Ready for structured review.",
          missing_slots: [],
          slots: {
            core_premise: { value: "Premise", complete: true },
            audience_genre: { value: "Genre", complete: true },
            tone_themes: { value: "Tone", complete: true },
            visual_style: { value: "Style", complete: true },
            world_rules: { value: "Rules", complete: true },
            core_cast: { value: "Cast", complete: true },
            character_identity: { value: "Identity", complete: true },
            relationship_baselines: { value: "Relationships", complete: true },
            constraints: { value: "Constraints", complete: true },
          },
          brief_draft_ready: true,
          chapter_draft: [],
          outline_draft_ready: false,
          updated_at: "",
        }}
        projectName="test"
        onPromoteBriefDraft={vi.fn()}
        onPromoteOutlineDraft={vi.fn()}
      />
    )

    expect(screen.getByTestId("intake-progress-panel")).toHaveTextContent("Next: enter Brief Review")
    expect(screen.getByRole("button", { name: /enter brief review/i })).toBeInTheDocument()
  })

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
