import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it } from 'vitest'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// happy-dom has no layout: give each tab a 100px slot so the indicator can measure.
const props = ['offsetWidth', 'offsetHeight', 'offsetLeft'] as const
const saved = props.map((p) => [p, Object.getOwnPropertyDescriptor(HTMLElement.prototype, p)])

function tabIndex(el: HTMLElement) {
  return el.getAttribute('role') === 'tab'
    ? [...(el.parentElement?.querySelectorAll('[role="tab"]') ?? [])].indexOf(el)
    : -1
}

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get(this: HTMLElement) {
      if (tabIndex(this) >= 0) return 100
      return this.dataset.slot === 'tabs-list' ? 300 : 0
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) {
      return tabIndex(this) >= 0 || this.dataset.slot === 'tabs-list' ? 30 : 0
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetLeft', {
    configurable: true,
    get(this: HTMLElement) {
      return Math.max(0, tabIndex(this)) * 100
    },
  })
})

afterEach(() => {
  cleanup()
  for (const [p, d] of saved) {
    if (d) Object.defineProperty(HTMLElement.prototype, p as string, d as PropertyDescriptor)
  }
})

function Example() {
  return (
    <Tabs defaultValue="script">
      <TabsList>
        <TabsTrigger value="script">Script</TabsTrigger>
        <TabsTrigger value="history">History</TabsTrigger>
        <TabsTrigger value="research">Research</TabsTrigger>
      </TabsList>
      <TabsContent value="script">Script body</TabsContent>
      <TabsContent value="history">History body</TabsContent>
      <TabsContent value="research">Research body</TabsContent>
    </Tabs>
  )
}

const indicator = () =>
  document.querySelector<HTMLElement>('[data-slot="tabs-indicator"]') as HTMLElement

it('slides one indicator to the selected tab', async () => {
  render(<Example />)
  await waitFor(() =>
    expect(indicator().style.getPropertyValue('--active-tab-width')).toBe('100px'),
  )
  expect(indicator().style.getPropertyValue('--active-tab-left')).toBe('0px')

  fireEvent.click(screen.getByRole('tab', { name: 'Research' }))
  await waitFor(() => expect(indicator().style.getPropertyValue('--active-tab-left')).toBe('200px'))
  expect(document.querySelectorAll('[data-slot="tabs-indicator"]')).toHaveLength(1)
  expect(screen.getByRole('tab', { name: 'Research' }).getAttribute('aria-selected')).toBe('true')
})

it('animates panels only after a real switch', async () => {
  render(<Example />)
  expect(screen.getByText('Script body').hasAttribute('data-switched')).toBe(false)
  fireEvent.click(screen.getByRole('tab', { name: 'History' }))
  await waitFor(() => expect(screen.getByText('History body')).toBeTruthy())
  expect(screen.getByText('History body').hasAttribute('data-switched')).toBe(true)
})

it('never switches motion off globally', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/assets/main.css'), 'utf8')
  expect(css).not.toContain('animation: none !important')
  expect(css).not.toContain('prefers-reduced-motion')
  expect(css).toContain('transform var(--tab-move)')
})
