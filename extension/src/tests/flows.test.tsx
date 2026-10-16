import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it } from 'vitest'
import { FlowBlock } from '@/components/script/FlowBlock'
import { initialStates } from '@/lib/api/mock/fixtures'
import type { FlowNode } from '@/lib/api/types'
import type { TemplateCtx } from '@/lib/script/template'

afterEach(cleanup)

const s = initialStates.c_glow as NonNullable<(typeof initialStates)[string]>
const ctx = {
  contact: s.context.contact,
  fields: {},
  computed: {},
  slots: {},
  slotsPending: false,
  omitAi: true,
  callerFirstName: 'Sam',
} as TemplateCtx

const flow: FlowNode = {
  ask: 'How many a month?',
  options: [
    {
      id: 'few',
      label: 'Under 10',
      say: 'Doable.',
      next: {
        ask: 'Which service?',
        options: [{ id: 'hrt', label: 'HRT', say: 'Strong area.' }],
      },
    },
    { id: 'many', label: 'Over 30', say: 'Ambitious.' },
  ],
}

function Harness() {
  const [ticked, setTicked] = useState<string[]>([])
  return (
    <FlowBlock
      node={flow}
      contactId="c"
      ticked={ticked}
      onToggle={(id) => setTicked((t) => (t.includes(id) ? t.filter((x) => x !== id) : [...t, id]))}
      ctx={ctx}
    />
  )
}

it('opens the next question only after an answer is ticked, level by level', () => {
  render(<Harness />)
  expect(screen.getByText('How many a month?')).toBeTruthy()
  expect(screen.queryByText('Which service?')).toBeNull()
  expect(screen.queryByText('HRT')).toBeNull()
  fireEvent.click(screen.getByText('Under 10'))
  expect(screen.getByText('Which service?')).toBeTruthy()
  expect(screen.getByText('Strong area.')).toBeTruthy()
  fireEvent.click(screen.getByText('Under 10'))
  expect(screen.queryByText('Which service?')).toBeNull()
  expect(screen.queryByText('HRT')).toBeNull()
})
