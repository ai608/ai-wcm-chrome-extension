import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api/errors'
import { __resetMock } from '@/lib/api/mock/handlers'

describe('mock api', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    __resetMock()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function mock() {
    return import('@/lib/api/mock/handlers')
  }

  it('logs in with demo, totp and rejects bad passwords', async () => {
    const api = await mock()
    const ok = api.login('sdr@example.com', 'demo')
    const okAssert = expect(ok).resolves.toMatchObject({ user: { email: 'sdr@example.com' } })
    await vi.advanceTimersByTimeAsync(600)
    await okAssert

    const totpRequired = api.login('sdr@example.com', 'totp')
    const totpAssert = expect(totpRequired).rejects.toMatchObject({ code: 'totp_required' })
    await vi.advanceTimersByTimeAsync(600)
    await totpAssert

    const totp = api.login('sdr@example.com', 'totp', '123456')
    const totpOk = expect(totp).resolves.toMatchObject({ user: { email: 'sdr@example.com' } })
    await vi.advanceTimersByTimeAsync(600)
    await totpOk

    const bad = api.login('sdr@example.com', 'wrong')
    const badAssert = expect(bad).rejects.toMatchObject({ code: 'invalid_credentials' })
    await vi.advanceTimersByTimeAsync(600)
    await badAssert
  })

  it('serves fixtures, 404s unknown contacts, and rejects annual_revenue on c_fail', async () => {
    const api = await mock()
    const p = api.getContactContext('c_glow')
    const ctxAssert = expect(p).resolves.toMatchObject({
      contact: { companyName: 'Glow Aesthetics Med Spa' },
      enrichment: { status: 'enriched' },
    })
    await vi.advanceTimersByTimeAsync(600)
    await ctxAssert

    const missing = api.getContactContext('c_nope')
    const missingAssert = expect(missing).rejects.toMatchObject({ code: 'contact_not_found' })
    await vi.advanceTimersByTimeAsync(600)
    await missingAssert

    const badPatch = api.patchFields('c_fail', { 'contact.annual_revenue': 100 })
    const patchAssert = expect(badPatch).rejects.toBeInstanceOf(ApiError)
    await vi.advanceTimersByTimeAsync(600)
    await patchAssert
  })

  it('runs enrich and generation transitions', async () => {
    const api = await mock()
    const first = api.getContactContext('c_vital')
    const firstAssert = expect(first).resolves.toMatchObject({
      enrichment: { status: 'not_enriched' },
    })
    await vi.advanceTimersByTimeAsync(600)
    await firstAssert

    const enriching = api.enrichContact('c_vital')
    const enrichAssert = expect(enriching).resolves.toEqual({ status: 'enriching' })
    await vi.advanceTimersByTimeAsync(600)
    await enrichAssert

    await vi.advanceTimersByTimeAsync(3000)
    const after = api.getContactContext('c_vital')
    const afterAssert = expect(after).resolves.toMatchObject({
      enrichment: { status: 'enriched' },
    })
    await vi.advanceTimersByTimeAsync(600)
    await afterAssert

    const generating = api.getPersonalizedScript('c_vital')
    const genAssert = expect(generating).resolves.toMatchObject({ status: 'generating' })
    await vi.advanceTimersByTimeAsync(600)
    await genAssert

    await vi.advanceTimersByTimeAsync(3000)
    const ready = api.getPersonalizedScript('c_vital')
    const readyAssert = expect(ready).resolves.toMatchObject({ status: 'ready' })
    await vi.advanceTimersByTimeAsync(600)
    await readyAssert
    expect((await ready).slots.opener).toContain('Vital IV')
  })
})
