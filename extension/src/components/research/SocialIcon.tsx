import { Globe } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Network = 'facebook' | 'instagram' | 'tiktok' | 'youtube' | 'linkedin' | 'x'

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

const GLYPH: Record<Network, ReactNode> = {
  facebook: (
    <path
      fill="currentColor"
      d="M13.6 21v-8h2.7l.4-3.2h-3.1V7.8c0-.9.3-1.5 1.6-1.5h1.7V3.4c-.3 0-1.3-.1-2.4-.1-2.4 0-4.1 1.5-4.1 4.2v2.3H7.6V13h2.8v8z"
    />
  ),
  instagram: (
    <g {...stroke}>
      <rect x="4" y="4" width="16" height="16" rx="4.5" />
      <circle cx="12" cy="12" r="3.6" />
      <circle cx="16.8" cy="7.2" r=".6" fill="currentColor" />
    </g>
  ),
  tiktok: (
    <g {...stroke}>
      <path d="M14 4v10.2a3.3 3.3 0 1 1-3.3-3.3" />
      <path d="M14 4c.4 2.3 1.9 3.9 4.2 4.1" />
    </g>
  ),
  youtube: (
    <g>
      <rect
        x="3"
        y="6"
        width="18"
        height="12"
        rx="3.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path d="M10.2 9.4v5.2l4.4-2.6z" fill="currentColor" />
    </g>
  ),
  linkedin: (
    <g fill="currentColor">
      <circle cx="6.6" cy="6.8" r="1.7" />
      <rect x="5.1" y="9.6" width="3" height="9" />
      <path d="M10.6 9.6h2.8v1.3c.5-.9 1.6-1.5 2.9-1.5 2.7 0 3.3 1.8 3.3 4.1v5.1h-3v-4.5c0-1.1 0-2.3-1.5-2.3s-1.7 1.1-1.7 2.2v4.6h-3z" />
    </g>
  ),
  x: (
    <g {...stroke}>
      <path d="M5 4.5h3.6L19 19.5h-3.6z" />
      <path d="M18.6 4.5l-5.9 6.8M5.4 19.5l5.9-6.8" />
    </g>
  ),
}

export function SocialIcon({ network, className }: { network: string; className?: string }) {
  const known = network in GLYPH ? (network as Network) : null
  return (
    <span
      aria-hidden="true"
      className={cn(
        'grid size-8 shrink-0 place-items-center rounded-lg bg-background text-foreground ring-1 ring-border',
        className,
      )}
    >
      {known ? (
        <svg viewBox="0 0 24 24" className="size-[18px]" role="presentation">
          {GLYPH[known]}
        </svg>
      ) : (
        <Globe className="size-4" />
      )}
    </span>
  )
}
