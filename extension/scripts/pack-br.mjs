import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { brotliCompressSync, constants } from 'node:zlib'

const dir = fileURLToPath(new URL('../.output/chrome-mv3/', import.meta.url))
const out = fileURLToPath(new URL('../.output/wcm-sales-assistant-chrome.tar.br', import.meta.url))
const tar = execFileSync('tar', ['-C', dir, '-cf', '-', '.'], { maxBuffer: 1 << 28 })
const br = brotliCompressSync(tar, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } })
writeFileSync(out, br)
console.log(`${out}\n${br.length} bytes (tar ${tar.length})`)
