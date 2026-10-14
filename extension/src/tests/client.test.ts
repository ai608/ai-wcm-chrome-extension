import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { ApiError } from '@/lib/api/errors'

function stubEnv() {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
}

function jsonResponse(status: number, data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const TOKENS = { accessToken: 'a1', refreshToken: 'r1', expiresAt: '2030-01-01T00:00:00Z' }

describe('api client', () => {
  beforeEach(() => {
    fakeBrowser.reset()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    stubEnv()
  })

  async function load() {
    const [{ request }, storage] = await Promise.all([
      import('@/lib/api/client'),
      import('@/lib/storage'),
    ])
    return { request, authItem: storage.authItem, authUserItem: storage.authUserItem }
  }

  it('parses the error envelope', async () => {
    const { request, authItem } = await load()
    await authItem.setValue(TOKENS)
    const fetchFn = vi.fn(async () =>
      jsonResponse(422, { error: { code: 'validation_error', message: 'Bad field' } }),
    )
    const err = await request('PATCH', '/contacts/c_1/fields', { body: {} }, fetchFn).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('validation_error')
    expect((err as ApiError).status).toBe(422)
  })

  it('maps fetch rejection to network_error', async () => {
    const { request } = await load()
    const fetchFn = vi.fn(async () => {
      throw new TypeError('down')
    })
    const err = await request('GET', '/me', {}, fetchFn).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('network_error')
  })

  it('shares one refresh across concurrent 401s', async () => {
    const { request, authItem } = await load()
    await authItem.setValue(TOKENS)
    let refreshCalls = 0
    const fetchFn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const u = String(url)
      if (u.endsWith('/auth/refresh')) {
        refreshCalls += 1
        return jsonResponse(200, {
          access_token: 'a2',
          refresh_token: 'r2',
          expires_at: '2030-01-01T00:00:00Z',
        })
      }
      const headers = init?.headers as Record<string, string> | undefined
      if (headers?.Authorization === 'Bearer a2') return jsonResponse(200, { ok: true })
      return jsonResponse(401, { error: { code: 'token_expired', message: 'expired' } })
    })
    const results = await Promise.all([
      request('GET', '/me', {}, fetchFn),
      request('GET', '/me', {}, fetchFn),
      request('GET', '/me', {}, fetchFn),
    ])
    expect(results).toHaveLength(3)
    expect(refreshCalls).toBe(1)
    expect((await authItem.getValue())?.accessToken).toBe('a2')
  })

  it('clears auth when refresh fails', async () => {
    const { request, authItem, authUserItem } = await load()
    await authItem.setValue(TOKENS)
    await authUserItem.setValue({
      id: 'u1',
      email: 'sdr@example.com',
      fullName: 'Sam Rep',
      role: 'user',
      hasExtensionAccess: true,
    })
    const fetchFn = vi.fn(async (url: string | URL | Request) => {
      if (String(url).endsWith('/auth/refresh'))
        return jsonResponse(401, { error: { code: 'unauthorized', message: 'nope' } })
      return jsonResponse(401, { error: { code: 'token_expired', message: 'expired' } })
    })
    const err = await request('GET', '/me', {}, fetchFn).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    await expect(authItem.getValue()).resolves.toBeNull()
    await expect(authUserItem.getValue()).resolves.toBeNull()
  })

  it('retries GET on 429 then succeeds', async () => {
    const { request } = await load()
    let calls = 0
    const fetchFn = vi.fn(async () => {
      calls += 1
      if (calls === 1)
        return jsonResponse(429, { error: { code: 'rate_limited', message: 'slow' } })
      return jsonResponse(200, { ok: true })
    })
    await expect(request('GET', '/me', { auth: false }, fetchFn)).resolves.toEqual({ ok: true })
    expect(calls).toBe(2)
  })

  it('never auto-retries POST outcome', async () => {
    const { request } = await load()
    let calls = 0
    const fetchFn = vi.fn(async () => {
      calls += 1
      return jsonResponse(503, { error: { code: 'upstream_error', message: 'down' } })
    })
    const err = await request('POST', '/contacts/c_1/outcome', { body: {} }, fetchFn).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiError)
    expect(calls).toBe(1)
  })
})
