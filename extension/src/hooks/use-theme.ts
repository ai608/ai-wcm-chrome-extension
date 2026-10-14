import { useEffect, useState } from 'react'
import { themeItem } from '@/lib/storage'

export type Theme = 'light' | 'dark' | 'system'

const mq = () => window.matchMedia('(prefers-color-scheme: dark)')
const resolveDark = (theme: Theme) => theme === 'dark' || (theme === 'system' && mq().matches)

function apply(theme: Theme, animate: boolean) {
  const root = document.documentElement
  if (animate) {
    root.classList.add('theme-transition')
    setTimeout(() => root.classList.remove('theme-transition'), 300)
  }
  root.classList.toggle('dark', resolveDark(theme))
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>('system')
  const [isDark, setIsDark] = useState(() => resolveDark('system'))

  useEffect(() => {
    themeItem.getValue().then(setThemeState)
    return themeItem.watch(setThemeState)
  }, [])

  useEffect(() => {
    // first apply (restoring saved theme) is instant; later changes fade
    apply(theme, document.documentElement.dataset.themeReady === '1')
    document.documentElement.dataset.themeReady = '1'
    setIsDark(resolveDark(theme))
    if (theme !== 'system') return
    const m = mq()
    const onChange = () => {
      apply('system', true)
      setIsDark(m.matches)
    }
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
  }, [theme])

  return { theme, isDark, toggle: () => themeItem.setValue(isDark ? 'light' : 'dark') }
}
