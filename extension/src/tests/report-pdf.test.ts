import { describe, expect, it, vi } from 'vitest'
import { buildPdf, headingBlock, pageCuts, paginate } from '@/lib/report-pdf'

describe('pageCuts', () => {
  it('keeps a short report on one page', () => {
    expect(pageCuts(800, 1000, [], [])).toEqual([0])
  })

  it('fills a page before starting the next one', () => {
    expect(pageCuts(1800, 1000, [], [])).toEqual([0, 1000])
  })

  it('keeps an explicit break and then fills each following page', () => {
    expect(pageCuts(2500, 1000, [400], [])).toEqual([0, 400, 1400, 2400])
  })

  it('moves a cut up so a section is not sliced', () => {
    expect(pageCuts(2000, 1000, [], [{ top: 900, bottom: 1100 }])).toEqual([0, 900, 1900])
  })
})

describe('paginate', () => {
  it('uses a shorter height on later pages when one is given', () => {
    expect(paginate(3000, 1000, 800, [])).toEqual([0, 1000, 1800, 2600])
  })
})

describe('headingBlock', () => {
  it('keeps a kicker, heading, and first row together', () => {
    expect(
      headingBlock(
        { top: 900, bottom: 920 },
        { top: 920, bottom: 960 },
        { top: 960, bottom: 1040 },
        1000,
      ),
    ).toEqual({ top: 900, bottom: 1040 })
  })

  it('does not glue a heading to a block taller than the page', () => {
    expect(
      headingBlock(null, { top: 100, bottom: 140 }, { top: 140, bottom: 1200 }, 1000),
    ).toBeNull()
  })
})

describe('buildPdf', () => {
  it('writes a multi-page PDF document', () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9])
    const bytes = buildPdf([
      { jpeg, width: 100, height: 120 },
      { jpeg, width: 100, height: 120 },
    ])
    const text = new TextDecoder().decode(bytes)
    expect(text.startsWith('%PDF-1.4')).toBe(true)
    expect(text).toContain('/Count 2')
    expect(text).toContain('%%EOF')
  })
})

describe('downloadReportPdf', () => {
  it('rasterizes the clone inside .report-root so the report styles still apply', async () => {
    let scoped: boolean | null = null
    vi.resetModules()
    vi.doMock('html-to-image', () => ({
      getFontEmbedCSS: async () => '',
      toCanvas: async (el: HTMLElement) => {
        scoped = el.closest('.report-root') !== null
        throw new Error('stop after the check')
      },
    }))
    Object.defineProperty(document, 'fonts', {
      value: { ready: Promise.resolve() },
      configurable: true,
    })
    const { downloadReportPdf } = await import('@/lib/report-pdf')
    const source = document.createElement('div')
    document.body.appendChild(source)
    await expect(downloadReportPdf(source)).rejects.toThrow('stop after the check')
    expect(scoped).toBe(true)
    vi.doUnmock('html-to-image')
  })
})
