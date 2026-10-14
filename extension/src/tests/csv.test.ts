import { describe, expect, it } from 'vitest'
import { toCsv } from '@/lib/csv'

describe('toCsv', () => {
  it('prefixes a BOM and uses CRLF', () => {
    const out = toCsv([{ a: 1, b: 'x' }])
    expect(out.startsWith('﻿')).toBe(true)
    expect(out).toBe('﻿a,b\r\n1,x')
  })

  it('quotes commas, quotes and newlines', () => {
    const out = toCsv([{ t: 'a,b', q: 'say "hi"', n: 'l1\nl2' }])
    expect(out).toBe('﻿t,q,n\r\n"a,b","say ""hi""","l1\nl2"')
  })

  it('keeps unicode and renders null/boolean', () => {
    expect(toCsv([{ a: 'Zoë – 患者', b: null, c: false }])).toBe('﻿a,b,c\r\nZoë – 患者,,false')
  })

  it('handles no rows', () => {
    expect(toCsv([])).toBe('﻿')
  })
})
