import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChapterOutlineWorkspaceView } from './ChapterOutlineWorkspaceView'

function createOutline(allConfirmed: boolean) {
  return {
    chapters: [
      {
        chapter_id: 'ch1',
        order: 1,
        chapter_name: 'Chapter 1',
        chapter_goal: 'goal',
        key_conflict: 'conflict',
        emotional_arc: 'arc',
        reveals: 'reveals',
        end_state: 'end',
        mood_or_pacing_bias: 'mood',
        character_focus: [],
        relationship_shift: '',
        character_presentation_notes: '',
        confirmed: allConfirmed,
      },
      {
        chapter_id: 'ch2',
        order: 2,
        chapter_name: 'Chapter 2',
        chapter_goal: 'goal',
        key_conflict: 'conflict',
        emotional_arc: 'arc',
        reveals: 'reveals',
        end_state: 'end',
        mood_or_pacing_bias: 'mood',
        character_focus: [],
        relationship_shift: '',
        character_presentation_notes: '',
        confirmed: allConfirmed,
      },
    ],
    updated_at: '',
  }
}

describe('ChapterOutlineWorkspaceView next-step CTA', () => {
  it('should summarize chapter confirmation progress in the review header', () => {
    const outline = createOutline(true)
    outline.chapters[0].confirmed = false

    render(
      <ChapterOutlineWorkspaceView
        outline={outline}
        projectName="test"
        onSave={vi.fn()}
        onConfirmChapter={vi.fn()}
      />
    )

    const header = screen.getByTestId('outline-review-header')

    expect(header).toHaveTextContent('Review progress')
    expect(header).toHaveTextContent('1 / 2 chapters confirmed')
    expect(header).toHaveTextContent('1 remaining')
  })

  it('should show freeze blueprint button when all chapters are confirmed', () => {
    render(
      <ChapterOutlineWorkspaceView
        outline={createOutline(true)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmChapter={vi.fn()}
        onFreezeBlueprint={vi.fn()}
      />
    )

    expect(
      screen.getByRole('button', { name: /freeze blueprint/i })
    ).toBeInTheDocument()
  })

  it('should NOT show freeze blueprint button when some chapters are unconfirmed', () => {
    const outline = createOutline(true)
    outline.chapters[0].confirmed = false

    render(
      <ChapterOutlineWorkspaceView
        outline={outline}
        projectName="test"
        onSave={vi.fn()}
        onConfirmChapter={vi.fn()}
        onFreezeBlueprint={vi.fn()}
      />
    )

    expect(
      screen.queryByRole('button', { name: /freeze blueprint/i })
    ).not.toBeInTheDocument()
  })

  it('should call onFreezeBlueprint when the freeze button is clicked', async () => {
    const user = userEvent.setup()
    const onFreezeBlueprint = vi.fn()

    render(
      <ChapterOutlineWorkspaceView
        outline={createOutline(true)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmChapter={vi.fn()}
        onFreezeBlueprint={onFreezeBlueprint}
      />
    )

    const btn = screen.getByRole('button', { name: /freeze blueprint/i })
    await user.click(btn)

    expect(onFreezeBlueprint).toHaveBeenCalledTimes(1)
  })
})

describe('ChapterOutlineWorkspaceView action error handling', () => {
  it('should keep the draft and show an inline error when saving fails', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockRejectedValue(new Error('outline save failed'))

    render(
      <ChapterOutlineWorkspaceView
        outline={createOutline(false)}
        projectName="test"
        onSave={onSave}
        onConfirmChapter={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /^edit$/i }))
    const nameInput = screen.getByDisplayValue('Chapter 1')
    await user.clear(nameInput)
    await user.type(nameInput, 'Renamed Chapter')
    await user.click(screen.getByRole('button', { name: /save/i }))

    const errorBox = await screen.findByTestId('outline-action-error')
    expect(errorBox).toHaveTextContent('outline save failed')
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    expect(screen.getByDisplayValue('Renamed Chapter')).toBeInTheDocument()
  })

  it('should show an inline error and re-enable the chapter when confirming fails', async () => {
    const user = userEvent.setup()
    const onConfirmChapter = vi.fn().mockRejectedValue(new Error('chapter confirm failed'))

    render(
      <ChapterOutlineWorkspaceView
        outline={createOutline(false)}
        projectName="test"
        onSave={vi.fn()}
        onConfirmChapter={onConfirmChapter}
      />
    )

    const confirmButtons = screen.getAllByRole('button', { name: /^confirm$/i })
    await user.click(confirmButtons[0])

    const errorBox = await screen.findByTestId('outline-action-error')
    expect(errorBox).toHaveTextContent('chapter confirm failed')
    expect(confirmButtons[0]).toBeEnabled()
  })
})
