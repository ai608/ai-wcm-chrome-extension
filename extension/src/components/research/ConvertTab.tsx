import { Block, Row } from '@/components/research/shared'
import type { ConvertSection } from '@/lib/api/research-types'

const yn = (b: boolean) => (b ? 'Yes' : 'No')

export function ConvertTab({ convert: c }: { convert: ConvertSection }) {
  return (
    <div className="flex flex-col gap-3">
      <Block title="Booking & contact">
        <Row label="Booking platform" status={c.bookingPlatform ? 'ok' : 'fail'}>
          {c.bookingPlatform ?? 'No online booking detected'}
        </Row>
        <Row label="Phone in header">{yn(c.phoneInHeader)}</Row>
        <Row label="Click-to-call">{yn(c.clickToCall)}</Row>
        <Row label="Forms">{c.formsCount}</Row>
        <Row label="Chat widget">{c.chatWidget ?? 'None'}</Row>
        <Row label="CTA above fold">{yn(c.ctaAboveFold)}</Row>
        <Row label="Offers / specials">{yn(c.offersOrSpecials)}</Row>
        <Row label="Financing">{yn(c.financingMentioned)}</Row>
        <Row label="Text us">{yn(c.textUs)}</Row>
      </Block>
      <Block title="Checks">
        {c.checks.map((k) => (
          <Row key={k.key} label={k.label} status={k.status}>
            {k.note}
          </Row>
        ))}
      </Block>
    </div>
  )
}
