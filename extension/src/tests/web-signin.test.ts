import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

async function load() {
  const signin = await import('@/lib/web-signin')
  const { authHandoffItem } = await import('@/lib/storage')
  return { ...signin, authHandoffItem }
}

describe('web sign-in handoff', () => {
  beforeEach(() => {
    fakeBrowser.reset()
    vi.stubGlobal('browser', fakeBrowser)
  })
  afterEach(() => {
    fakeBrowser.reset()
    vi.unstubAllGlobals()
  })

  it('a second click joins the sign-in under way instead of replacing it', async () => {
    const { beginHandoff, takeHandoff } = await load()
    const first = await beginHandoff(1_000)
    const second = await beginHandoff(5_000)
    expect(second).toEqual(first) // the first tab's sign-in still works
    expect(await takeHandoff(first.state, 6_000)).not.toBeNull()
    expect(await takeHandoff(second.state, 7_000)).toBeNull() // used once; the other tab is a no-op
  })

  it('an expired sign-in is cleared and a new click starts a fresh one', async () => {
    const { beginHandoff, takeHandoff, authHandoffItem, HANDOFF_MAX_AGE_MS } = await load()
    const old = await beginHandoff(0)
    expect(await takeHandoff(old.state, HANDOFF_MAX_AGE_MS + 1)).toBeNull()
    await expect(authHandoffItem.getValue()).resolves.toBeNull() // cleared, not left behind
    const again = await beginHandoff(HANDOFF_MAX_AGE_MS + 2)
    expect(again.state).not.toBe(old.state)
  })

  it('a click after the window starts a fresh sign-in even if nothing took the old one', async () => {
    const { beginHandoff, HANDOFF_MAX_AGE_MS } = await load()
    const old = await beginHandoff(0)
    const fresh = await beginHandoff(HANDOFF_MAX_AGE_MS + 1)
    expect(fresh.state).not.toBe(old.state)
  })

  it('a message with another state changes nothing and does not cancel the real sign-in', async () => {
    const { beginHandoff, takeHandoff, authHandoffItem } = await load()
    const real = await beginHandoff(0)
    expect(await takeHandoff('forged', 1_000)).toBeNull()
    expect(await takeHandoff(undefined, 1_000)).toBeNull()
    await expect(authHandoffItem.getValue()).resolves.not.toBeNull()
    expect(await takeHandoff(real.state, 2_000)).not.toBeNull()
  })

  it('gives the verifier only to the matching state, and the challenge is its hash', async () => {
    const { beginHandoff, takeHandoff, authHandoffItem } = await load()
    const { state, challenge } = await beginHandoff(0)
    const stored = await authHandoffItem.getValue()
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stored?.verifier))
    const expected = btoa(String.fromCharCode(...new Uint8Array(hash)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    expect(challenge).toBe(expected)
    expect(await takeHandoff(state, 1)).toEqual({ verifier: stored?.verifier })
  })
})
