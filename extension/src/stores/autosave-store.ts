import { create } from 'zustand'
import { queryClient } from '@/app/providers'
import { qk } from '@/hooks/queries'
import { ApiError } from '@/lib/api/errors'
import type { ContactContext, FieldValue } from '@/lib/api/types'
import { call } from '@/lib/messaging'

export type FieldStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error'
export type InputClass = 'slow' | 'fast'

const SLOW_MS = 800
const FAST_MS = 300
const BATCH_MS = 50
const SAVED_FADE_MS = 2000

interface AutosaveState {
  queue: Record<string, Record<string, FieldValue>>
  status: Record<string, Record<string, FieldStatus>>
  errors: Record<string, Record<string, string>>
  failStreak: Record<string, number>
  lastError: Record<string, ApiError | null>
  inFlight: Record<string, boolean>
}

interface AutosaveActions {
  setField: (contactId: string, fieldKey: string, value: FieldValue, input: InputClass) => void
  flush: (contactId: string) => void
  flushAll: () => void
  retry: (contactId: string, fieldKey: string) => void
}

const timers = new Map<string, ReturnType<typeof setTimeout>>()
const batchTimers = new Map<string, ReturnType<typeof setTimeout>>()
const savedTimers = new Map<string, ReturnType<typeof setTimeout>>()

function timerKey(contactId: string, fieldKey: string) {
  return `${contactId}::${fieldKey}`
}

function clearTimer(key: string, pool: Map<string, ReturnType<typeof setTimeout>>) {
  const t = pool.get(key)
  if (t) {
    clearTimeout(t)
    pool.delete(key)
  }
}

function setStatus(contactId: string, fieldKey: string, status: FieldStatus) {
  useAutosaveStore.setState((s) => ({
    status: { ...s.status, [contactId]: { ...s.status[contactId], [fieldKey]: status } },
  }))
}

function writeCache(contactId: string, fields: Record<string, FieldValue>) {
  queryClient.setQueryData<ContactContext>(qk.contactContext(contactId), (old) => {
    if (!old) return old
    return { ...old, fieldValues: { ...old.fieldValues, ...fields } }
  })
}

async function sendPatch(contactId: string) {
  const store = useAutosaveStore.getState()
  if (store.inFlight[contactId]) return
  const fields = store.queue[contactId]
  if (!fields || Object.keys(fields).length === 0) return

  useAutosaveStore.setState((s) => ({ inFlight: { ...s.inFlight, [contactId]: true } }))
  for (const key of Object.keys(fields)) setStatus(contactId, key, 'saving')

  try {
    const result = await call('patchFields', { contactId, fields })
    writeCache(contactId, result.fieldValues)
    useAutosaveStore.setState((s) => {
      const queue = { ...s.queue }
      const remaining = { ...(queue[contactId] ?? {}) }
      for (const key of Object.keys(fields)) delete remaining[key]
      if (Object.keys(remaining).length === 0) delete queue[contactId]
      else queue[contactId] = remaining
      return { queue, failStreak: { ...s.failStreak, [contactId]: 0 } }
    })
    for (const key of Object.keys(fields)) {
      setStatus(contactId, key, 'saved')
      const tk = timerKey(contactId, key)
      clearTimer(tk, savedTimers)
      savedTimers.set(
        tk,
        setTimeout(() => {
          const cur = useAutosaveStore.getState().status[contactId]?.[key]
          if (cur === 'saved') setStatus(contactId, key, 'idle')
          savedTimers.delete(tk)
        }, SAVED_FADE_MS),
      )
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Could not save'
    useAutosaveStore.setState((s) => {
      const streak = (s.failStreak[contactId] ?? 0) + 1
      return {
        errors: {
          ...s.errors,
          [contactId]: {
            ...s.errors[contactId],
            ...Object.fromEntries(Object.keys(fields).map((k) => [k, message])),
          },
        },
        failStreak: { ...s.failStreak, [contactId]: streak },
        lastError: {
          ...s.lastError,
          [contactId]:
            streak >= 3 && err instanceof ApiError ? err : (s.lastError[contactId] ?? null),
        },
      }
    })
    for (const key of Object.keys(fields)) setStatus(contactId, key, 'error')
  } finally {
    useAutosaveStore.setState((s) => ({ inFlight: { ...s.inFlight, [contactId]: false } }))
    const current = useAutosaveStore.getState().queue[contactId] ?? {}
    const changed =
      Object.keys(current).length !== Object.keys(fields).length ||
      Object.entries(fields).some(([k, v]) => JSON.stringify(current[k]) !== JSON.stringify(v))
    if (changed) void sendPatch(contactId)
  }
}

function scheduleBatch(contactId: string) {
  if (batchTimers.has(contactId)) return
  batchTimers.set(
    contactId,
    setTimeout(() => {
      batchTimers.delete(contactId)
      void sendPatch(contactId)
    }, BATCH_MS),
  )
}

export const useAutosaveStore = create<AutosaveState & AutosaveActions>()((set, get) => ({
  queue: {},
  status: {},
  errors: {},
  failStreak: {},
  lastError: {},
  inFlight: {},

  setField: (contactId, fieldKey, value, input) => {
    writeCache(contactId, { [fieldKey]: value })
    set((s) => ({
      queue: { ...s.queue, [contactId]: { ...s.queue[contactId], [fieldKey]: value } },
    }))
    setStatus(contactId, fieldKey, 'pending')
    const tk = timerKey(contactId, fieldKey)
    clearTimer(tk, timers)
    timers.set(
      tk,
      setTimeout(
        () => {
          timers.delete(tk)
          scheduleBatch(contactId)
        },
        input === 'fast' ? FAST_MS : SLOW_MS,
      ),
    )
  },

  flush: (contactId) => {
    for (const [key, t] of timers) {
      if (key.startsWith(`${contactId}::`)) {
        clearTimeout(t)
        timers.delete(key)
      }
    }
    clearTimer(contactId, batchTimers)
    const pending = get().queue[contactId]
    if (pending && Object.keys(pending).length > 0) void sendPatch(contactId)
  },

  flushAll: () => {
    for (const contactId of Object.keys(get().queue)) get().flush(contactId)
  },

  retry: (contactId, fieldKey) => {
    const value = get().queue[contactId]?.[fieldKey]
    if (value === undefined) return
    setStatus(contactId, fieldKey, 'pending')
    scheduleBatch(contactId)
  },
}))

export function __resetAutosave() {
  for (const t of timers.values()) clearTimeout(t)
  for (const t of batchTimers.values()) clearTimeout(t)
  for (const t of savedTimers.values()) clearTimeout(t)
  timers.clear()
  batchTimers.clear()
  savedTimers.clear()
  useAutosaveStore.setState({
    queue: {},
    status: {},
    errors: {},
    failStreak: {},
    lastError: {},
    inFlight: {},
  })
}
