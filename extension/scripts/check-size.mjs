import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

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
const rows = files.map((f) => ({ file: f.replace(outDir, ''), gz: gzipSync(readFileSync(f)).length }))

console.log('file\tgzipped bytes')
for (const r of rows) console.log(`${r.file}\t${r.gz}`)
const sidepanel = rows.filter((r) => r.file.includes('sidepanel')).reduce((a, r) => a + r.gz, 0)
const background = rows.filter((r) => r.file.includes('background')).reduce((a, r) => a + r.gz, 0)
console.log(`sidepanel total gz: ${sidepanel}`)
console.log(`background total gz: ${background}`)

let fail = false
if (sidepanel > 250 * 1024) {
  console.error('FAIL: side-panel JS exceeds 250 KB gzipped')
  fail = true
}
if (background > 40 * 1024) {
  console.error('FAIL: background JS exceeds 40 KB gzipped')
  fail = true
}
process.exit(fail ? 1 : 0)
