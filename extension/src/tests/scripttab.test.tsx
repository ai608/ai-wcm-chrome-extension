import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ScriptTab } from '@/components/script/ScriptTab'
import { initialStates, scriptDefinition } from '@/lib/api/mock/fixtures'

vi.mock('@/lib/messaging', () => ({ call: async () => ({}) }))

afterEach(cleanup)

it('renders the full script without an update loop', () => {
  const s = initialStates.c_glow as NonNullable<(typeof initialStates)[string]>
  const state = {
    definition: scriptDefinition,
    definitionPending: false,
    definitionError: null,
    context: s.context,
    contextPending: false,
    contextError: null,
    script: s.script,
    scriptPending: false,
    timedOut: false,
    enrichPending: false,
    regeneratePending: false,
    startEnrich: () => {},
    startRegenerate: () => {},
  }
  // biome-ignore lint/suspicious/noExplicitAny: partial state stub
  const { container } = render(
    <ScriptTab
      contactId="c_glow"
      callerFirstName="Sam"
      bookingWidgetUrl="about:blank"
      state={state as any}
    />,
  )
  expect(container.textContent).toContain('Opener')
  fireEvent.click(screen.getByText('Opener'))
  fireEvent.click(screen.getByText('Qualification'))
  fireEvent.click(screen.getByText('Opener'))
  fireEvent.click(container.querySelector('[role="checkbox"]') as Element)
})
