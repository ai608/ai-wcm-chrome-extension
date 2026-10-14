import { Fragment } from 'react'

const URL_RE = /(https?:\/\/[^\s]+)/g

export function linkify(body: string): React.ReactNode[] {
  const parts = body.split(URL_RE)
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      return (
        <a key={i} href={part} target="_blank" rel="noreferrer" className="text-primary underline">
          {part}
        </a>
      )
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}
