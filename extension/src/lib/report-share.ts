const EXT_URL = /url\((['"]?)(chrome-extension:\/\/[^)'"]+)\1\)/g

async function dataUrl(url: string): Promise<string> {
  const blob = await (await fetch(url)).blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/** Extension-only URLs (fonts, logo) mean nothing to a visitor, so they are inlined. */
async function inlineUrls(css: string): Promise<string> {
  const urls = [...new Set([...css.matchAll(EXT_URL)].map((m) => m[2] ?? ''))]
  const data = new Map(await Promise.all(urls.map(async (u) => [u, await dataUrl(u)] as const)))
  return css.replace(EXT_URL, (_m, _q, u: string) => `url("${data.get(u)}")`)
}

/** The rendered report as one self-contained HTML document, for a public link. */
export async function reportSnapshot(): Promise<string> {
  const root = document.querySelector('.report-root')
  if (!(root instanceof HTMLElement)) throw new Error('report not ready')
  const copy = root.cloneNode(true) as HTMLElement
  await Promise.all(
    [...copy.querySelectorAll('img')].map(async (img) => {
      if (img.src.startsWith('chrome-extension://')) img.src = await dataUrl(img.src)
    }),
  )
  const css = [...document.styleSheets]
    .map((sheet) => [...sheet.cssRules].map((r) => r.cssText).join('\n'))
    .join('\n')
  const style = await inlineUrls(css)
  const title = document.title.replace(/[<&]/g, '')
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${title}</title><style>${style}</style></head><body>${copy.outerHTML}</body></html>`
}
