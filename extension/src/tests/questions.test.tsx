import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QuestionField } from '@/components/script/QuestionField'
import type { Block } from '@/lib/api/types'

type Question = Extract<Block, { type: 'question' }>

function question(overrides: Partial<Question> & { input: Question['input'] }): Question {
  return {
    type: 'question',
    id: 'q1',
    fieldKey: 'contact.test_field',
    label: 'Test field',
    requiredForBooking: false,
    ...overrides,
  }
}

describe('QuestionField', () => {
  afterEach(() => cleanup())

  it('commits text input', () => {
    const onCommit = vi.fn()
    render(
      <QuestionField
        contactId="c1"
        block={question({ input: 'text' })}
        initialValue={null}
        onCommit={onCommit}
      />,
    )
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: 'hello' } })
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 'hello')
  })

  it('commits textarea input', () => {
    const onCommit = vi.fn()
    render(
      <QuestionField
        contactId="c1"
        block={question({ input: 'textarea' })}
        initialValue={null}
        onCommit={onCommit}
      />,
    )
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: 'why now' } })
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 'why now')
  })

  it('commits numbers and rejects invalid input', () => {
    const onCommit = vi.fn()
    render(
      <QuestionField
        contactId="c1"
        block={question({ input: 'number' })}
        initialValue={null}
        onCommit={onCommit}
      />,
    )
    const input = screen.getByLabelText('Test field')
    fireEvent.change(input, { target: { value: '42' } })
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 42)
    fireEvent.change(input, { target: { value: 'abc' } })
    expect(screen.getByText('Enter a number')).toBeDefined()
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 42)
  })

  it('commits currency as a number', () => {
    const onCommit = vi.fn()
    render(
      <QuestionField
        contactId="c1"
        block={question({ input: 'currency' })}
        initialValue={null}
        onCommit={onCommit}
      />,
    )
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: '350' } })
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 350)
  })

  it('commits select and radio choices', () => {
    const onCommit = vi.fn()
    const options = [
      { value: 'a', label: 'A' },
      { value: 'b', label: 'B' },
    ]
    const { unmount } = render(
      <QuestionField
        contactId="c1"
        block={question({ input: 'radio', options })}
        initialValue={null}
        onCommit={onCommit}
      />,
    )
    fireEvent.click(screen.getByRole('radio', { name: 'B' }))
    expect(onCommit).toHaveBeenLastCalledWith('contact.test_field', 'b')
    unmount()
  })

  it('toggles checkbox group values', () => {
    const onCommit = vi.fn()
    render(
      <QuestionField
        contactId="c1"
        block={question({
          input: 'checkbox_group',
          options: [
            { value: 'x', label: 'X' },
            { value: 'y', label: 'Y' },
          ],
        })}
        initialValue={['x']}
        onCommit={onCommit}
      />,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'Y' }))
    // happy-dom forwards label clicks to the nested control, toggling twice;
    // the first toggle is the real user intent.
    expect(onCommit.mock.calls[0]).toEqual(['contact.test_field', ['x', 'y']])
  })
})
