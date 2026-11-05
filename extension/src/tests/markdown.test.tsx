import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Markdown } from '@/lib/markdown'

describe('Markdown', () => {
  it('renders bold, a link, and a list without leaving the marks', () => {
    render(
      <Markdown
        text={'**Dr. Lee:** leads the group.\n\nSee [the clinic](https://example.com).\n\n- Botox\n- IV therapy'}
      />,
    )
    expect(screen.getByText('Dr. Lee:').tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*/)).toBeNull()
    const link = screen.getByRole('link', { name: 'the clinic' })
    expect(link.getAttribute('href')).toBe('https://example.com')
    expect(screen.getByText('Botox').closest('li')).toBeTruthy()
    expect(screen.getByText('IV therapy').closest('li')).toBeTruthy()
  })
})
