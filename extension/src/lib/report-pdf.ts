import { getFontEmbedCSS, toCanvas } from 'html-to-image'

const PAGE_W = 816
const PAGE_H = Math.round(PAGE_W * (11 / 8.5))
/** Quiet folio sits in this band so it never covers the last line. */
const PAGE_FOOTER = 36
const PAGE_INSET = 28
/** Air above the content on every page but the first (the cover has its own masthead). */
const PAGE_TOP = 36
/** Rasterize the vector layout at 2× so type and rules stay sharp in the file. */
const RASTER = 2

type Block = { top: number; bottom: number }

/** Pulls a cut up to the nearest block that would otherwise be sliced. */
function snapCut(y: number, next: number, pageHeight: number, blocks: Block[]): number {
  const minChunk = pageHeight * 0.45
  const hit = blocks
    .filter(
      (b) =>
        b.top > y + minChunk && b.top < next && b.bottom > next && b.bottom - b.top < pageHeight,
    )
    .sort((a, b) => b.top - a.top)[0]
  return hit ? hit.top : next
}

/** A heading, its kicker, and the first row under them stay on the same page. */
export function headingBlock(
  kicker: Block | null,
  heading: Block,
  firstRow: Block | null,
  pageHeight: number,
): Block | null {
  const top = kicker && kicker.top <= heading.top ? kicker.top : heading.top
  let bottom = Math.max(heading.bottom, kicker?.bottom ?? 0)
  if (firstRow && firstRow.top >= top) bottom = Math.max(bottom, firstRow.bottom)
  if (bottom <= top || bottom - top >= pageHeight) return null
  return { top, bottom }
}

/** Later pages can be shorter when a caller reserves a different band. */
export function paginate(
  height: number,
  firstHeight: number,
  restHeight: number,
  blocks: Block[],
): number[] {
  if (height <= 0 || firstHeight <= 0) return [0]
  if (height <= firstHeight + 1) return [0]
  let y = snapCut(0, firstHeight, firstHeight, blocks)
  if (y <= 8) y = firstHeight
  const cuts = [0, y]
  const step = restHeight > 0 ? restHeight : firstHeight
  while (height - y > step + 1) {
    const next = snapCut(y, y + step, step, blocks)
    if (next <= y + 8) break
    cuts.push(next)
    y = next
  }
  return cuts
}

export function pageCuts(
  height: number,
  pageHeight: number,
  forced: number[],
  blocks: Block[],
): number[] {
  if (height <= 0 || pageHeight <= 0) return [0]
  const points = [...new Set([0, ...forced.filter((y) => y > 1 && y < height - 1), height])].sort(
    (a, b) => a - b,
  )
  const cuts = [0]
  for (let i = 0; i < points.length - 1; i++) {
    let y = points[i] ?? 0
    const end = points[i + 1] ?? height
    const last = cuts[cuts.length - 1] ?? 0
    if (y > last + 1) cuts.push(y)
    while (end - y > pageHeight + 1) {
      const next = snapCut(y, y + pageHeight, pageHeight, blocks)
      if (next <= y + 8) break
      cuts.push(next)
      y = next
    }
  }
  return cuts
}

export function buildPdf(pages: { jpeg: Uint8Array; width: number; height: number }[]): Uint8Array {
  if (pages.length === 0) throw new Error('no pages')
  const enc = new TextEncoder()
  const chunks: Uint8Array[] = []
  let length = 0
  const push = (part: string | Uint8Array) => {
    const bytes = typeof part === 'string' ? enc.encode(part) : part
    chunks.push(bytes)
    length += bytes.length
  }
  const objs: { id: number; at: number }[] = []
  const startObj = (id: number) => {
    objs.push({ id, at: length })
    push(`${id} 0 obj\n`)
  }
  const endObj = () => push('\nendobj\n')

  push('%PDF-1.4\n')
  startObj(1)
  push('<< /Type /Catalog /Pages 2 0 R >>')
  endObj()
  const kids = pages.map((_, i) => `${3 + i * 3} 0 R`).join(' ')
  startObj(2)
  push(`<< /Type /Pages /Count ${pages.length} /Kids [${kids}] >>`)
  endObj()

  const pageW = 612
  const pageH = 792
  for (const [i, page] of pages.entries()) {
    const pageId = 3 + i * 3
    const imgId = pageId + 1
    const contentId = pageId + 2
    const drawH = Math.min(pageH, pageW * (page.height / page.width))
    const content = `q\n${pageW} 0 0 ${drawH.toFixed(2)} 0 ${(pageH - drawH).toFixed(2)} cm\n/Im0 Do\nQ\n`
    startObj(pageId)
    push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] /Resources << /XObject << /Im0 ${imgId} 0 R >> >> /Contents ${contentId} 0 R >>`,
    )
    endObj()
    startObj(imgId)
    push(
      `<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpeg.length} >>\nstream\n`,
    )
    push(page.jpeg)
    push('\nendstream')
    endObj()
    startObj(contentId)
    push(`<< /Length ${enc.encode(content).length} >>\nstream\n${content}endstream`)
    endObj()
  }

  const xrefAt = length
  const size = objs.length + 1
  push(`xref\n0 ${size}\n`)
  push('0000000000 65535 f \n')
  for (let id = 1; id < size; id++) {
    const at = objs.find((o) => o.id === id)?.at ?? 0
    push(`${String(at).padStart(10, '0')} 00000 n \n`)
  }
  push(`trailer\n<< /Size ${size} /Root 1 0 R >>\nstartxref\n${xrefAt}\n%%EOF`)

  const out = new Uint8Array(length)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.length
  }
  return out
}

function fileName(root: ParentNode): string {
  const domain = root.querySelector('.report-meta p')?.textContent?.trim() || 'report'
  const safe = domain.replace(/[^a-z0-9.-]+/gi, '-').replace(/^-|-$/g, '') || 'report'
  return `${safe}-visibility-report.pdf`
}

function measure(root: HTMLElement) {
  const base = root.getBoundingClientRect().top
  const topOf = (el: Element) => (el as HTMLElement).getBoundingClientRect().top - base
  const box = (el: Element): Block => {
    const top = topOf(el)
    return { top, bottom: top + (el as HTMLElement).offsetHeight }
  }
  const blocks = [
    ...root.querySelectorAll('.report-grade, .report-tile, .report-row, .report-table tr'),
  ].map(box)
  for (const heading of root.querySelectorAll('h2')) {
    const prev = heading.previousElementSibling
    const kicker =
      prev instanceof HTMLElement &&
      prev.classList.contains('report-kicker') &&
      !prev.classList.contains('report-kicker-quiet')
        ? prev
        : null
    const scope = heading.closest('section') ?? heading.parentElement
    const row = scope
      ? [...scope.querySelectorAll('.report-row, .report-gbp')].find(
          (el) => topOf(el) >= topOf(heading),
        )
      : null
    const span = headingBlock(
      kicker ? box(kicker) : null,
      box(heading),
      row ? box(row) : null,
      PAGE_H,
    )
    if (span) blocks.push(span)
  }
  return { height: root.scrollHeight, blocks }
}

function slicePage(
  source: HTMLCanvasElement,
  sy: number,
  sh: number,
  pagePx: number,
  chrome: { label: string; top: number },
): Promise<Uint8Array> {
  const page = document.createElement('canvas')
  page.width = source.width
  page.height = pagePx
  const ctx = page.getContext('2d')
  if (!ctx) throw new Error('canvas unavailable')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, page.width, page.height)
  const top = chrome.top * RASTER
  const drawH = Math.min(sh, pagePx - top)
  ctx.drawImage(source, 0, sy, source.width, drawH, 0, top, source.width, drawH)
  const inset = PAGE_INSET * RASTER
  ctx.fillStyle = '#1a1a1a'
  ctx.font = `${12 * RASTER}px Poppins, sans-serif`
  ctx.textBaseline = 'middle'
  const foot = page.height - (PAGE_FOOTER * RASTER) / 2
  ctx.textAlign = 'left'
  ctx.fillText('Wellness Clinic Marketing', inset, foot)
  ctx.textAlign = 'right'
  ctx.fillText(chrome.label, page.width - inset, foot)
  return new Promise((resolve, reject) => {
    page.toBlob(
      async (blob) => {
        if (!blob) {
          reject(new Error('empty page'))
          return
        }
        resolve(new Uint8Array(await blob.arrayBuffer()))
      },
      'image/jpeg',
      0.92,
    )
  })
}

function saveFile(bytes: Uint8Array, name: string) {
  const copy = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer
  const blob = new Blob([copy], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

async function waitForImages(root: ParentNode) {
  const imgs = [...root.querySelectorAll('img')]
  await Promise.all(
    imgs.map((img) =>
      img.complete && img.naturalWidth > 0
        ? Promise.resolve()
        : new Promise((resolve) => {
            img.onload = () => resolve(null)
            img.onerror = () => resolve(null)
          }),
    ),
  )
}

async function rasterPage(
  frame: HTMLElement,
  sliceH: number,
  fontEmbedCSS: string,
  chrome: { label: string; top: number },
): Promise<Uint8Array> {
  const canvas = await toCanvas(frame, {
    pixelRatio: RASTER,
    backgroundColor: '#ffffff',
    width: PAGE_W,
    height: Math.max(1, Math.round(sliceH)),
    fontEmbedCSS,
    skipAutoScale: true,
  })
  const pagePx = Math.round(PAGE_H * RASTER)
  return slicePage(canvas, 0, canvas.height, pagePx, chrome)
}

/** Rasterizes the vector layout into a PDF file. Does not open the print dialog. */
export async function downloadReportPdf(source: HTMLElement): Promise<void> {
  const started = performance.now()
  const host = document.createElement('div')
  // The report's colors, tick/cross fills and score bars are styled as `.report-root ...`. The
  // clone sits outside the page's own .report-root, so without this class they all drop out.
  host.className = 'report-root'
  host.style.cssText = `position:fixed;left:-10000px;top:0;width:${PAGE_W}px;background:#fff;`
  const frame = document.createElement('div')
  frame.style.cssText = `width:${PAGE_W}px;overflow:hidden;background:#fff;`
  const shift = document.createElement('div')
  const node = source.cloneNode(true) as HTMLElement
  node.style.width = `${PAGE_W}px`
  node.style.maxWidth = `${PAGE_W}px`
  node.style.tableLayout = 'fixed'
  shift.appendChild(node)
  frame.appendChild(shift)
  host.appendChild(frame)
  document.body.appendChild(host)
  try {
    await document.fonts.ready
    await waitForImages(host)
    if (node.scrollWidth > PAGE_W + 1) {
      console.warn('[report] pdf wider than page', {
        scrollWidth: node.scrollWidth,
        page: PAGE_W,
      })
    }
    const { height, blocks } = measure(node)
    const pageH = PAGE_H - PAGE_FOOTER
    const cuts = paginate(height, pageH, pageH - PAGE_TOP, blocks)
    console.info('[report] pdf paginate', { height, pageH, pages: cuts.length, cuts })
    const fontEmbedCSS = await getFontEmbedCSS(node)
    const pages: { jpeg: Uint8Array; width: number; height: number }[] = []
    for (let i = 0; i < cuts.length; i++) {
      const y = cuts[i] ?? 0
      const end = i + 1 < cuts.length ? (cuts[i + 1] ?? height) : height
      const sliceH = Math.max(1, end - y)
      shift.style.marginTop = `${-y}px`
      frame.style.height = `${sliceH}px`
      const jpeg = await rasterPage(frame, sliceH, fontEmbedCSS, {
        label: `${i + 1} of ${cuts.length}`,
        top: i === 0 ? 0 : PAGE_TOP,
      })
      pages.push({ jpeg, width: PAGE_W * RASTER, height: Math.round(PAGE_H * RASTER) })
    }
    const name = fileName(node)
    saveFile(buildPdf(pages), name)
    console.info('[report] pdf saved', {
      pages: pages.length,
      file: name,
      raster: RASTER,
      ms: Math.round(performance.now() - started),
    })
  } finally {
    host.remove()
  }
}
