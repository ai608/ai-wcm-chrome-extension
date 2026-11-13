import { ApiError } from '@/lib/api/errors'
import { getEnv } from '@/lib/env'
import { authItem, authUserItem } from '@/lib/storage'

export interface RequestOptions {
  body?: unknown
  auth?: boolean
  signal?: AbortSignal
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string }
}

const TIMEOUT_MS = 20_000
const RETRY_DELAYS = [500, 1500]

/** `ok`: new tokens saved. `denied`: the server says the session is over (sign out).
 * `unreachable`: no answer or a server error, which says nothing about the session (stay signed in). */
type RefreshResult = 'ok' | 'denied' | 'unreachable'

let refreshPromise: Promise<RefreshResult> | null = null

async function refreshOnce(fetchFn: typeof fetch): Promise<RefreshResult> {
  const auth = await authItem.getValue()
  if (!auth) return 'denied'
  try {
    const res = await fetchFn(`${getEnv().apiBaseUrl}/api/v1/ext/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: auth.refreshToken }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
    if (res.status === 401 || res.status === 403) return 'denied'
    if (!res.ok) return 'unreachable'
    const data = (await res.json()) as {
      access_token: string
      refresh_token: string
      expires_at: string
    }
    await authItem.setValue({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresAt: data.expires_at,
    })
    return 'ok'
  } catch {
    return 'unreachable'
  }
}

async function doRefresh(fetchFn: typeof fetch): Promise<RefreshResult> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    try {
      // One more try after a pause: the answer may have been lost on its way back, and the
      // server accepts the token it just replaced for a short time (REFRESH_GRACE).
      const first = await refreshOnce(fetchFn)
      if (first !== 'unreachable') return first
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS[0]))
      return await refreshOnce(fetchFn)
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

async function clearAuth() {
  await authItem.setValue(null)
  await authUserItem.setValue(null)
}

function toApiError(status: number, payload: unknown, fallbackCode: string): ApiError {
  const envelope = payload as ErrorEnvelope | null
  const code = envelope?.error?.code ?? fallbackCode
  const message = envelope?.error?.message ?? `Request failed with status ${status}`
  return new ApiError(status, code, message)
}

export async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
  fetchFn: typeof fetch = fetch,
): Promise<T> {
  const env = getEnv()
  const { body, auth = true, signal } = options
  const retryable = method === 'GET' || method === 'PATCH'

  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  const combined = signal ? AbortSignal.any([timeout, signal]) : timeout

  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const tokens = await authItem.getValue()
    if (tokens) headers.Authorization = `Bearer ${tokens.accessToken}`
  }

  let refreshed = false
  let attempt = 0
  for (;;) {
    let res: Response
    try {
      res = await fetchFn(`${env.apiBaseUrl}/api/v1/ext${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: combined,
      })
    } catch {
      throw new ApiError(0, 'network_error', "You're offline")
    }

    if (res.ok) {
      if (res.status === 204) return undefined as T
      return (await res.json()) as T
    }

    let payload: unknown = null
    try {
      payload = await res.json()
    } catch {
      payload = null
    }

    const code = (payload as ErrorEnvelope | null)?.error?.code
    if (res.status === 403 && auth && code === 'no_extension_access') {
      await clearAuth()
      throw toApiError(res.status, payload, code)
    }
    if (
      res.status === 401 &&
      auth &&
      !refreshed &&
      (code === 'unauthorized' || code === 'token_expired')
    ) {
      refreshed = true
      const result = await doRefresh(fetchFn)
      if (result === 'ok') {
        const tokens = await authItem.getValue()
        if (tokens) headers.Authorization = `Bearer ${tokens.accessToken}`
        continue
      }
      // Only a refusal ends the session; a network or server error must not sign anyone out.
      if (result === 'denied') await clearAuth()
      throw toApiError(res.status, payload, code ?? 'unauthorized')
    }

    if (
      retryable &&
      (res.status === 429 || res.status === 502 || res.status === 503) &&
      attempt < RETRY_DELAYS.length
    ) {
      const delay = RETRY_DELAYS[attempt] ?? 1500
      attempt += 1
      await new Promise((r) => setTimeout(r, delay))
      continue
    }

    throw toApiError(res.status, payload, code ?? 'upstream_error')
  }
}
