import { authHandoffItem } from '@/lib/storage'

/** A sign-in that was started and not finished is valid this long. */
export const HANDOFF_MAX_AGE_MS = 10 * 60_000

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

async function challengeOf(verifier: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return base64url(new Uint8Array(hash))
}

/**
 * Start a sign-in, or join the one already under way. A second click (a second tab, a double
 * click) used to replace the first sign-in's secret, so whichever page finished first failed.
 * Now every page opened within the window carries the same `state`: the first to finish signs
 * in, and a leftover one finds nothing waiting and does nothing.
 */
export async function beginHandoff(
  now: number = Date.now(),
): Promise<{ state: string; challenge: string }> {
  const pending = await authHandoffItem.getValue()
  if (pending && now - pending.createdAt <= HANDOFF_MAX_AGE_MS) {
    return { state: pending.state, challenge: await challengeOf(pending.verifier) }
  }
  const state = base64url(crypto.getRandomValues(new Uint8Array(32)))
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)))
  await authHandoffItem.setValue({ state, verifier, createdAt: now }) // replaces an expired one
  return { state, challenge: await challengeOf(verifier) }
}

/**
 * Take the waiting sign-in for this `state`, once. An expired one is cleared. A `state` that is
 * not the waiting one (a stray or forged message) changes nothing: it must not cancel a real
 * sign-in that is still under way.
 */
export async function takeHandoff(
  state: unknown,
  now: number = Date.now(),
): Promise<{ verifier: string } | null> {
  const pending = await authHandoffItem.getValue()
  if (!pending) return null
  if (now - pending.createdAt > HANDOFF_MAX_AGE_MS) {
    await authHandoffItem.setValue(null)
    return null
  }
  if (state !== pending.state) return null
  await authHandoffItem.setValue(null)
  return { verifier: pending.verifier }
}
