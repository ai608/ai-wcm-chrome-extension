import type { SiteSection } from '@/lib/api/research-types'

export type Area = NonNullable<SiteSection['cities']['areas']>[number]

/** What is wrong with an area's own page, in words a salesperson can say to the clinic. */
export function areaProblems(a: Area): string[] {
  return a.issues.map((i) =>
    i === 'noindex'
      ? 'hidden from Google'
      : i === 'thin'
        ? 'thin (under 300 words)'
        : i === 'title_h1'
          ? 'city missing from title and heading'
          : `copies ${a.duplicateOf ?? 'another city'}'s page`,
  )
}
