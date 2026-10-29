import { MapPin } from 'lucide-react'
import mapBanner from '@/assets/map-banner.webp'

/**
 * A map picture (a generated image, not live data) with a pin, linked to the real Google Maps listing. The picture is an
 * illustration, not the clinic's actual surroundings, so the link caption says where it goes.
 */
export function StaticMap({ href, label }: { href: string | null; label: string }) {
  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      className="group relative block h-36 w-full overflow-hidden rounded-lg bg-muted focus-visible:outline-2 focus-visible:outline-ring"
    >
      <img
        src={mapBanner}
        alt=""
        draggable={false}
        className="absolute inset-0 size-full select-none object-cover"
      />
      <MapPin
        aria-hidden="true"
        className="absolute top-1/2 left-1/2 size-8 -translate-x-1/2 -translate-y-full fill-destructive text-white drop-shadow"
      />
      <span className="absolute right-2 bottom-2 rounded-md bg-background/90 px-2 py-0.5 text-[11px] font-medium text-foreground shadow-sm group-hover:bg-background">
        Open in Google Maps
      </span>
    </a>
  )
}
