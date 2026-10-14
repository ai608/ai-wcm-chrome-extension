import { Block, Chip, ExtLink, Row } from '@/components/research/shared'
import type { Audit, SchemaSection } from '@/lib/api/research-types'

export function SchemaTab({ audit, schema }: { audit: Audit; schema: SchemaSection }) {
  return (
    <div className="flex flex-col gap-3">
      <Block>
        <Row
          label="JSON-LD blocks"
          status={schema.parseErrors ? 'fail' : schema.jsonLdCount ? 'ok' : 'warn'}
        >
          {schema.jsonLdCount} found,{' '}
          {schema.parseErrors ? `${schema.parseErrors} parse errors` : 'all parse cleanly'}
        </Row>
        <Row label="LocalBusiness" status={schema.hasLocalBusiness ? 'ok' : 'fail'}>
          {schema.hasLocalBusiness
            ? 'Present'
            : 'No LocalBusiness-type schema anywhere on the page'}
        </Row>
        <Row label="FAQPage" status={schema.hasFaqPage ? 'ok' : 'warn'}>
          {schema.hasFaqPage ? 'Present' : 'Missing'}
        </Row>
        <Row label="Review markup" status={schema.hasReviewMarkup ? 'ok' : 'warn'}>
          {schema.hasReviewMarkup ? 'Present' : 'Missing'}
        </Row>
      </Block>
      <ExtLink
        href={`https://search.google.com/test/rich-results?url=${encodeURIComponent(audit.url)}`}
      >
        Validate in Rich Results Test
      </ExtLink>
      {schema.blocks.map((b, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: a type can repeat; order is identity
        <Block key={`${b.type}-${i}`} title={b.type}>
          <div className="flex flex-wrap gap-1.5">
            {b.presentProps.map((p) => (
              <Chip key={p} tone="good">
                ✓ {p}
              </Chip>
            ))}
            {b.missingRecommended.map((p) => (
              <Chip key={p} tone="warn">
                {p}
              </Chip>
            ))}
          </div>
        </Block>
      ))}
      <details className="rounded-lg border border-border p-3">
        <summary className="cursor-pointer text-[14px] font-semibold">Raw JSON</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[12px]">
          {schema.raw}
        </pre>
      </details>
    </div>
  )
}
