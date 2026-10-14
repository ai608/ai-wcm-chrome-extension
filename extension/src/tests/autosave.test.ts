import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '@/app/providers'
import { qk } from '@/hooks/queries'
import type { ContactContext } from '@/lib/api/types'
import { __resetAutosave, useAutosaveStore } from '@/stores/autosave-store'

const callMock = vi.fn()

vi.mock('@/lib/messaging', () => ({
  call: (...args: unknown[]) => callMock(...args),
}))

function seedCache(
  contactId: string,
  fieldValues: Record<string, string | number | string[] | null> = {},
) {
  queryClient.setQueryData<ContactContext>(qk.contactContext(contactId), {
    contact: {
      id: contactId,
      firstName: 'M',
      lastName: 'R',
      companyName: 'Glow',
      email: '',
      phone: '',
      city: '',
      state: '',
      postalCode: '',
      website: '',
      tags: [],
    },
    fieldValues,
    enrichment: {
      status: 'enriched',
      services: [],
      googleRating: null,
      googleReviewCount: null,
      score: null,
      updatedAt: null,
    },
  })
}

function status(contactId: string, fieldKey: string) {
  return useAutosaveStore.getState().status[contactId]?.[fieldKey] ?? 'idle'
}

describe('autosave store', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    __resetAutosave()
    queryClient.clear()
    callMock.mockReset()
    callMock.mockImplementation(
      async (_type: string, data: { fields: Record<string, unknown> }) => ({
        fieldValues: data.fields,
        updatedAt: '2026-10-14T00:00:00Z',
      }),
    )
    seedCache('c1')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces slow inputs and batches fields into one PATCH', async () => {
    const { setField } = useAutosaveStore.getState()
    setField('c1', 'contact.a', 'one', 'slow')
    setField('c1', 'contact.b', 'two', 'slow')
    expect(callMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(850)
    expect(callMock).toHaveBeenCalledTimes(1)
    expect(callMock.mock.calls[0]?.[1]).toEqual({
      contactId: 'c1',
      fields: { 'contact.a': 'one', 'contact.b': 'two' },
    })
    expect(status('c1', 'contact.a')).toBe('saved')
  })

  it('uses the fast delay for selects', async () => {
    const { setField } = useAutosaveStore.getState()
    setField('c1', 'contact.s', 'v', 'fast')
    await vi.advanceTimersByTimeAsync(350)
    expect(callMock).toHaveBeenCalledTimes(1)
  })

  it('writes the query cache optimistically', () => {
    const { setField } = useAutosaveStore.getState()
    setField('c1', 'contact.a', 'draft', 'slow')
    const cached = queryClient.getQueryData<ContactContext>(qk.contactContext('c1'))
    expect(cached?.fieldValues['contact.a']).toBe('draft')
    expect(status('c1', 'contact.a')).toBe('pending')
  })

  it('marks error and retries', async () => {
    callMock.mockRejectedValueOnce(new Error('down'))
    const { setField, retry } = useAutosaveStore.getState()
    setField('c1', 'contact.a', 'x', 'fast')
    await vi.advanceTimersByTimeAsync(400)
    expect(status('c1', 'contact.a')).toBe('error')
    retry('c1', 'contact.a')
    await vi.advanceTimersByTimeAsync(100)
    expect(callMock).toHaveBeenCalledTimes(2)
    expect(status('c1', 'contact.a')).toBe('saved')
  })

  it('flush sends pending edits immediately', async () => {
    const { setField, flush } = useAutosaveStore.getState()
    setField('c1', 'contact.a', 'x', 'slow')
    flush('c1')
    await vi.advanceTimersByTimeAsync(0)
    expect(callMock).toHaveBeenCalledTimes(1)
  })

  it('queues edits made while a PATCH is in flight', async () => {
    let release!: () => void
    const gate = new Promise<unknown>((r) => {
      release = () => r({ fieldValues: { 'contact.a': '1' }, updatedAt: 'x' })
    })
    callMock.mockImplementationOnce(() => gate)
    const { setField } = useAutosaveStore.getState()
    setField('c1', 'contact.a', '1', 'fast')
    await vi.advanceTimersByTimeAsync(400)
    expect(callMock).toHaveBeenCalledTimes(1)
    setField('c1', 'contact.b', '2', 'fast')
    await vi.advanceTimersByTimeAsync(400)
    expect(callMock).toHaveBeenCalledTimes(1)
    release()
    await vi.advanceTimersByTimeAsync(100)
    expect(callMock).toHaveBeenCalledTimes(2)
    expect(callMock.mock.calls[1]?.[1]).toEqual({ contactId: 'c1', fields: { 'contact.b': '2' } })
  })
})
