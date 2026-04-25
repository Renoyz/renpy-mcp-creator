import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BriefWorkspaceView } from './BriefWorkspaceView'

function createBrief(allConfirmed: boolean) {
  return {
    cards: {
      core_premise: { content: 'test premise', confirmed: allConfirmed },
      audience_genre: { content: 'test genre', confirmed: allConfirmed },
      tone_themes: { content: 'test tone', confirmed: allConfirmed },
      visual_style: { content: 'test visual', confirmed: allConfirmed },
      world_rules: { content: 'test rules', confirmed: allConfirmed },
      core_cast: { content: 'test cast', confirmed: allConfirmed },
      constraints: { content: 'test constraints', confirmed: allConfirmed },
      character_identity: { content: { characters: [] }, confirmed: allConfirmed },
      relationship_baselines: { content: { relationships: [] }, confirmed: allConfirmed },
    },
    updated_at: '',
  }
}

describe('BriefWorkspaceView next-step CTA', () => {
  it('should show the outline review CTA when all cards are confirmed and outline draft is ready', () => {
    render(
      <BriefWorkspaceView
        brief={createBrief(true)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={vi.fn()}
        onProceedToOutline={vi.fn()}
        outlineDraftReady
      />
    )

    expect(
      screen.getByRole('button', { name: /enter chapter outline review/i })
    ).toBeInTheDocument()
  })

  it('should NOT show a next-step button when some cards are unconfirmed', () => {
    const brief = createBrief(true)
    brief.cards.core_premise.confirmed = false

    render(
      <BriefWorkspaceView
        brief={brief}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={vi.fn()}
        onProceedToOutline={vi.fn()}
      />
    )

    expect(
      screen.queryByRole('button', { name: /enter chapter outline review/i })
    ).not.toBeInTheDocument()
  })

  it('should show chapter intake progress instead of outline CTA when outline draft is not ready', () => {
    render(
      <BriefWorkspaceView
        brief={createBrief(true)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={vi.fn()}
        onProceedToOutline={vi.fn()}
        onContinueChapterIntake={vi.fn()}
        outlineDraftReady={false}
      />
    )

    expect(
      screen.queryByRole('button', { name: /enter chapter outline review/i })
    ).not.toBeInTheDocument()
    expect(screen.getByText(/chapter intake in progress/i)).toBeInTheDocument()
    expect(screen.getByTestId('outline-draft-progress')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /continue chapter intake/i })).toBeInTheDocument()
  })

  it('should call onProceedToOutline when the outline review CTA is clicked', async () => {
    const user = userEvent.setup()
    const onProceedToOutline = vi.fn()

    render(
      <BriefWorkspaceView
        brief={createBrief(true)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={vi.fn()}
        onProceedToOutline={onProceedToOutline}
        outlineDraftReady
      />
    )

    const btn = screen.getByRole('button', { name: /enter chapter outline review/i })
    await user.click(btn)

    expect(onProceedToOutline).toHaveBeenCalledTimes(1)
  })
})
