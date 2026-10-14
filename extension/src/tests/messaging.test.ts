import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api/errors'

describe('messaging error round trip', () => {
  it('restores ApiError after structured-clone serialization', () => {
    const original = new ApiError(422, 'validation_error', 'annual_revenue: enter a valid amount')
    const wire = structuredClone(original.toJSON())
    const restored = ApiError.fromJSON(wire)
    expect(restored).toBeInstanceOf(ApiError)
    expect(restored?.status).toBe(422)
    expect(restored?.code).toBe('validation_error')
    expect(restored?.message).toBe('annual_revenue: enter a valid amount')
  })

  it('ignores non-error payloads', () => {
    expect(ApiError.fromJSON({ ok: true })).toBeNull()
    expect(ApiError.fromJSON(null)).toBeNull()
    expect(ApiError.fromJSON('boom')).toBeNull()
  })
})
