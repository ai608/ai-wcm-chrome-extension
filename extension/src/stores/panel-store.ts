import { create } from 'zustand'
import type { LastTab } from '@/lib/storage'

interface PanelState {
  view: 'main' | 'settings'
  activeTab: LastTab
  openSections: Record<string, boolean>
  tickedResponses: Record<string, string[]>
  pendingConfirm: 'regenerate' | 'signout' | 'rerun' | 'send_report' | null
  setView: (view: 'main' | 'settings') => void
  setActiveTab: (tab: LastTab) => void
  setSectionOpen: (sectionId: string, open: boolean) => void
  toggleResponse: (contactId: string, blockId: string) => void
  setPendingConfirm: (v: PanelState['pendingConfirm']) => void
  researchTab: string
  setResearchTab: (t: string) => void
  researchSubTab: Record<string, string>
  setResearchSubTab: (tab: string, v: string) => void
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
    set((s) =>
      s.openSections[sectionId] === open
        ? s
        : { openSections: { ...s.openSections, [sectionId]: open } },
    ),
  toggleResponse: (contactId, blockId) =>
    set((s) => {
      const current = s.tickedResponses[contactId] ?? []
      const next = current.includes(blockId)
        ? current.filter((b) => b !== blockId)
        : [...current, blockId]
      return { tickedResponses: { ...s.tickedResponses, [contactId]: next } }
    }),
  setPendingConfirm: (pendingConfirm) => set({ pendingConfirm }),
  researchTab: 'overview',
  setResearchTab: (researchTab) => set({ researchTab }),
  researchSubTab: {},
  setResearchSubTab: (tab, v) =>
    set((s) => ({ researchSubTab: { ...s.researchSubTab, [tab]: v } })),
}))
