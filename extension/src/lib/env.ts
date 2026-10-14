export interface Env {
  ghlHost: string
  apiBaseUrl: string
  apiMock: boolean
}

function required(name: string): string {
  const value = import.meta.env[name] as string | undefined
  if (!value || value.length === 0) throw new Error(`Missing required env var ${name}`)
  return value
}

export function getEnv(): Env {
  const apiBaseUrl = required('WXT_API_BASE_URL').replace(/\/$/, '')
  return {
    ghlHost: required('WXT_GHL_HOST'),
    apiBaseUrl,
    apiMock: (import.meta.env.WXT_API_MOCK as string | undefined) === 'true',
  }
}
