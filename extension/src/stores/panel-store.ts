import { create } from 'zustand'
import type { LastTab } from '@/lib/storage'

interface PanelState {
  view: 'main' | 'settings'
  activeTab: LastTab
  openSections: Record<string, boolean>
  tickedResponses: Record<string, string[]>
  pendingConfirm: 'regenerate' | 'signout' | null
  setView: (view: 'main' | 'settings') => void
  setActiveTab: (tab: LastTab) => void
  setSectionOpen: (sectionId: string, open: boolean) => void
  toggleResponse: (contactId: string, blockId: string) => void
  setPendingConfirm: (v: 'regenerate' | 'signout' | null) => void
}

export const usePanelStore = create<PanelState>()((set) => ({
  view: 'main',
  activeTab: 'script',
  openSections: {},
  tickedResponses: {},
  pendingConfirm: null,
  setView: (view) => set({ view }),
  setActiveTab: (activeTab) => set({ activeTab }),
  setSectionOpen: (sectionId, open) =>
    set((s) => ({ openSections: { ...s.openSections, [sectionId]: open } })),
  toggleResponse: (contactId, blockId) =>
    set((s) => {
      const current = s.tickedResponses[contactId] ?? []
      const next = current.includes(blockId)
        ? current.filter((b) => b !== blockId)
        : [...current, blockId]
      return { tickedResponses: { ...s.tickedResponses, [contactId]: next } }
    }),
  setPendingConfirm: (pendingConfirm) => set({ pendingConfirm }),
}))
