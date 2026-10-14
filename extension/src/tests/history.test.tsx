import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActivityCard } from '@/components/history/ActivityCard'
import { BriefCard } from '@/components/history/BriefCard'
import type { Activity } from '@/lib/api/types'

describe('history cards', () => {
  afterEach(() => cleanup())

  it('linkifies urls in activity bodies', () => {
    const activity: Activity = {
      id: 'a1',
      kind: 'note',
      source: 'Automation',
      createdAt: '2026-08-23T21:07:00Z',
      body: 'See https://example.com/report for details',
    }
    render(<ActivityCard activity={activity} />)
    const link = screen.getByRole('link', { name: 'https://example.com/report' })
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noreferrer')
    expect(screen.getByText('Automation')).toBeDefined()
  })

  it('clamps long bodies with show more and less', () => {
    const activity: Activity = {
      id: 'a2',
      kind: 'call',
      source: 'Sam Rivera',
      createdAt: '2026-08-23T21:07:00Z',
      body: Array.from({ length: 20 }, (_, i) => `line ${i}`).join('\n'),
    }
    const { container } = render(<ActivityCard activity={activity} />)
    expect(container.querySelector('.line-clamp-12')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(container.querySelector('.line-clamp-12')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show less' }))
    expect(container.querySelector('.line-clamp-12')).not.toBeNull()
  })

  it('warns when the contact is stale or never contacted', () => {
    render(
      <BriefCard
        brief={{ text: 'Summary', generatedAt: '2026-10-13T00:00:00Z' }}
        lastContactedAt={null}
      />,
    )
    expect(screen.getByText('Never contacted')).toBeDefined()
    cleanup()
    render(
      <BriefCard
        brief={{ text: 'Summary', generatedAt: '2026-10-13T00:00:00Z' }}
        lastContactedAt="2020-01-01T00:00:00Z"
      />,
    )
    expect(screen.getByText(/Not contacted in/)).toBeDefined()
  })
})
