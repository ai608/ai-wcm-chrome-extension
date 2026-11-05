import type { ReactNode } from 'react'

const INLINE =
  /\*\*([^*]+)\*\*|__([^_]+)__|(?<!\w)\*([^*]+)\*(?!\w)|`([^`]+)`|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g

/** Turns a model answer into text nodes. Raw HTML is never inserted. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let key = 0
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0
    if (index > last) out.push(text.slice(last, index))
    const id = key++
    if (match[1] || match[2]) out.push(<strong key={id}>{match[1] ?? match[2]}</strong>)
    else if (match[3]) out.push(<em key={id}>{match[3]}</em>)
    else if (match[4])
      out.push(
        <code key={id} className="text-[0.92em]">
          {match[4]}
        </code>,
      )
    else if (match[5] && match[6])
      out.push(
        <a
          key={id}
          href={match[6]}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline"
        >
          {match[5]}
        </a>,
      )
    last = index + match[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function isList(line: string, ordered: boolean): boolean {
  return ordered ? /^\d+\.\s+/.test(line) : /^[-*]\s+/.test(line)
}

/** Renders the markdown these answers actually use: bold, lists, headings, links. */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i] ?? ''
    if (!line.trim()) {
      i++
      continue
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      const Tag = (heading[1]?.length ?? 2) === 1 ? 'h3' : 'h4'
      blocks.push(
        <Tag key={key++} className="font-semibold">
          {inline(heading[2] ?? '')}
        </Tag>,
      )
      i++
      continue
    }
    if (isList(line, false) || isList(line, true)) {
      const ordered = isList(line, true)
      const items: ReactNode[] = []
      while (i < lines.length && isList(lines[i] ?? '', ordered)) {
        items.push(
          <li key={items.length}>{inline((lines[i] ?? '').replace(/^([-*]|\d+\.)\s+/, ''))}</li>,
        )
        i++
      }
      const List = ordered ? 'ol' : 'ul'
      blocks.push(
        <List key={key++} className={ordered ? 'list-decimal pl-5' : 'list-disc pl-5'}>
          {items}
        </List>,
      )
      continue
    }
    const parts = [line]
    i++
    while (
      i < lines.length &&
      (lines[i] ?? '').trim() &&
      !/^(#{1,3}\s|[-*]\s|\d+\.\s)/.test(lines[i] ?? '')
    ) {
      parts.push(lines[i] ?? '')
      i++
    }
    blocks.push(
      <p key={key++}>
        {parts.map((part, index) => (
          <span key={part}>
            {index > 0 ? <br /> : null}
            {inline(part)}
          </span>
        ))}
      </p>,
    )
  }
  return (
    <div className="flex flex-col gap-1.5 text-[14px] leading-relaxed text-foreground">{blocks}</div>
  )
}
