import { create } from 'zustand'

interface PanelState {
  view: 'main' | 'settings'
  setView: (view: 'main' | 'settings') => void
}

export const usePanelStore = create<PanelState>()((set) => ({
  view: 'main',
  setView: (view) => set({ view }),
}))
