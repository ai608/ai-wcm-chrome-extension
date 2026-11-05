import { create } from 'zustand'
import type { AiQuestions } from '@/lib/api/research-types'

/** Questions the user is reviewing for one audit, and the run size that came with them. */
export interface AiDraft {
  list: string[]
  plan: AiQuestions | null
}

interface AiDraftState {
  drafts: Record<string, AiDraft>
  setDraft: (auditId: string, draft: AiDraft) => void
  clearDraft: (auditId: string) => void
}

/**
 * Lives outside the panel, so switching to another tab (Local Competitors) and back, or to another
 * contact and back, keeps the questions. It is dropped when the user approves, cancels, or closes
 * the side panel. In memory only: unapproved questions are cheap to write again.
 */
export const useAiDraft = create<AiDraftState>()((set) => ({
  drafts: {},
  setDraft: (auditId, draft) => set((s) => ({ drafts: { ...s.drafts, [auditId]: draft } })),
  clearDraft: (auditId) =>
    set((s) => {
      const { [auditId]: _gone, ...rest } = s.drafts
      return { drafts: rest }
    }),
}))
