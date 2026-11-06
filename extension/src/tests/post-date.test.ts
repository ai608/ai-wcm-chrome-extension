import { describe, expect, it } from 'vitest'
import { formatPostDate } from '@/lib/time'

describe('formatPostDate', () => {
  it('shows the date as the site wrote it, whatever the viewer time zone', () => {
    // 20:24 UTC is already the 28th in India; the site (and this) say the 27th.
    const out = formatPostDate('2026-10-27T20:24:40+00:00')
    expect(out).toContain('27')
    expect(out).not.toContain('28')
  })
})
