import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliCompressSync, gzipSync } from 'node:zlib'

const outDir = fileURLToPath(new URL('../.output/chrome-mv3/', import.meta.url))

function jsFiles(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) out.push(...jsFiles(full))
    else if (entry.endsWith('.js')) out.push(full)
  }
  return out
}

const files = jsFiles(outDir)
const rows = files.map((f) => ({ file: f.replace(outDir, ''), gz: gzipSync(readFileSync(f)).length, br: brotliCompressSync(readFileSync(f)).length }))

console.log('file\tgzip\tbrotli')
for (const r of rows) console.log(`${r.file}\t${r.gz}\t${r.br}`)
const sum = (pred) => rows.filter(pred).reduce((a, r) => a + r.gz, 0)
const background = sum((r) => r.file.includes('background'))
const report = sum((r) => /(^|\/)report-/.test(r.file))
const panel = sum((r) => !r.file.includes('background') && !/(^|\/)report-/.test(r.file))
console.log(`side panel total gz (incl. lazy + shared chunks): ${panel}`)
console.log(`report page own chunks gz: ${report}`)
console.log(`background total gz: ${background}`)

let fail = false
const limit = (name, value, kb) => {
  if (value > kb * 1024) {
    console.error(`FAIL: ${name} exceeds ${kb} KB gzipped`)
    fail = true
  }
}
limit('side-panel JS', panel, 300)
limit('background JS', background, 40)
limit('report page JS', report, 60)
process.exit(fail ? 1 : 0)
