type Cell = string | number | boolean | null

function quote(v: Cell): string {
  const s = v == null ? '' : String(v)
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(rows: Record<string, Cell>[]): string {
  const first = rows[0]
  if (!first) return '﻿'
  const cols = Object.keys(first)
  const lines = [cols.map(quote).join(',')]
  for (const r of rows) lines.push(cols.map((c) => quote(r[c] ?? null)).join(','))
  return `﻿${lines.join('\r\n')}`
}

export function downloadCsv(domain: string, kind: string, csv: string) {
  const day = new Date().toISOString().slice(0, 10)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  a.download = `${domain}-${kind}-${day}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
