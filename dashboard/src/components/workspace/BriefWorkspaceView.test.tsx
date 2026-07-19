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
  it('should summarize brief confirmation progress in the review header', () => {
    const brief = createBrief(true)
    brief.cards.core_premise.confirmed = false

    render(
      <BriefWorkspaceView
        brief={brief}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={vi.fn()}
      />
    )

    const header = screen.getByTestId('brief-review-header')

    expect(header).toHaveTextContent('Review progress')
    expect(header).toHaveTextContent('8 / 9 confirmed')
    expect(header).toHaveTextContent('1 remaining')
  })

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

describe('BriefWorkspaceView action error handling', () => {
  it('should keep the draft and show an inline error when saving fails', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockRejectedValue(new Error('save failed: server exploded'))

    render(
      <BriefWorkspaceView
        brief={createBrief(false)}
        projectName="test"
        onSave={onSave}
        onConfirmCard={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /^edit$/i }))
    const premiseBox = screen.getByPlaceholderText('Enter Core Premise...')
    await user.clear(premiseBox)
    await user.type(premiseBox, 'edited premise draft')
    await user.click(screen.getByRole('button', { name: /save/i }))

    const errorBox = await screen.findByTestId('brief-action-error')
    expect(errorBox).toHaveTextContent('save failed: server exploded')
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter Core Premise...')).toHaveValue('edited premise draft')
  })

  it('should show an inline error and re-enable the card when confirming fails', async () => {
    const user = userEvent.setup()
    const onConfirmCard = vi.fn().mockRejectedValue(new Error('confirm failed'))

    render(
      <BriefWorkspaceView
        brief={createBrief(false)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmCard={onConfirmCard}
      />
    )

    const confirmButtons = screen.getAllByRole('button', { name: /^confirm$/i })
    await user.click(confirmButtons[0])

    const errorBox = await screen.findByTestId('brief-action-error')
    expect(errorBox).toHaveTextContent('confirm failed')
    expect(confirmButtons[0]).toBeEnabled()
  })
})
