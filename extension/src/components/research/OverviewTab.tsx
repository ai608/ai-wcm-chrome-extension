import { useState } from 'react'
import { Block, gradeClass, gradeText, InfoNote, SECTION_LABEL } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import { useSendReport } from '@/hooks/research-queries'
import { ApiError } from '@/lib/api/errors'
import type { Audit, SectionKey } from '@/lib/api/research-types'
import { call } from '@/lib/messaging'
import { getEnv } from '@/lib/env'
import { usePanelStore } from '@/stores/panel-store'

const CHECKLIST: SectionKey[] = ['on_page', 'schema', 'site', 'business', 'convert', 'overview']

export function quickToolLinks(auditUrl: string) {
  const u = new URL(auditUrl)
  const enc = encodeURIComponent(auditUrl)
  return [
    { label: 'robots.txt', href: new URL('/robots.txt', u.origin).toString() },
    { label: 'sitemap.xml', href: new URL('/sitemap.xml', u.origin).toString() },
    { label: 'PageSpeed', href: `https://pagespeed.web.dev/analysis?url=${enc}` },
    { label: 'Rich Results', href: `https://search.google.com/test/rich-results?url=${enc}` },
  ]
}

function Progressing({ audit }: { audit: Audit }) {
  return (
    <Block title="Running audit…">
      <ul className="flex flex-col gap-1 text-[13px]">
        {CHECKLIST.map((k) => {
          const s = audit.sectionState[k]
          const mark = s === 'ready' ? '✓' : s === 'failed' ? '⚠' : '…'
          return (
            <li key={k} className="flex gap-2">
              <span className="w-4 text-center" aria-hidden>
                {mark}
              </span>
              <span className={s === 'ready' ? '' : 'text-muted-foreground'}>
                {SECTION_LABEL[k]}
              </span>
              <span className="sr-only">{s}</span>
            </li>
          )
        })}
      </ul>
    </Block>
  )
}

function SendReport({ audit }: { audit: Audit }) {
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pending = usePanelStore((s) => s.pendingConfirm)
  const setPending = usePanelStore((s) => s.setPendingConfirm)
  const send = useSendReport(audit.id)

  async function submit() {
    setPending(null)
    setError(null)
    try {
      const r = await send.mutateAsync({ email, note: note || undefined })
      toast('Report sent')
      setResult(
        [
          `email ${r.emailSent ? '✓' : '✗'}`,
          `Slack ${r.slackSent ? '✓' : '✗'}`,
          r.ghlContactId ? `logged to GHL contact ${r.ghlContactId}` : 'GHL contact created',
        ].join(' · '),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the report')
    }
  }

  return (
    <Block title="Send report">
      <form
        className="flex flex-col gap-2.5"
        onSubmit={(e) => {
          e.preventDefault()
          setPending('send_report')
        }}
      >
        <div className="flex gap-2">
          <Label htmlFor="rr-email" className="sr-only">
            Email
          </Label>
          <Input
            id="rr-email"
            type="email"
            required
            placeholder="prospect@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" disabled={send.isPending} className="shrink-0 px-4 font-semibold">
            Send report
          </Button>
        </div>
        <Label htmlFor="rr-note" className="sr-only">
          Note (optional)
        </Label>
        <Textarea
          id="rr-note"
          rows={2}
          placeholder="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {pending === 'send_report' ? (
          <div className="flex items-center gap-2 text-[13px]">
            <span className="flex-1">Send the report to {email}?</span>
            <Button type="button" variant="outline" size="xs" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button type="button" size="xs" onClick={submit} disabled={send.isPending}>
              {send.isPending ? 'Sending…' : 'Send'}
            </Button>
          </div>
        ) : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {result ? <p className="text-[12px] text-muted-foreground">{result}</p> : null}
        <InfoNote>
          Emails the branded report to the prospect, logs it on their GHL contact in the Sales
          account, and alerts #marketing-alerts.
        </InfoNote>
      </form>
    </Block>
  )
}

export function OverviewTab({ audit }: { audit: Audit }) {
  const o = audit.overview
  if (!o) return <Progressing audit={audit} />
  const tools = quickToolLinks(audit.url)
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted/40 p-4">
        <div className="flex items-center gap-3">
          <div
            className={`flex size-16 shrink-0 items-center justify-center rounded-full text-3xl font-bold ${gradeClass(o.grade)}`}
          >
            {o.grade}
          </div>
          <div>
            <p className="text-xl font-bold leading-tight">{o.score} / 100</p>
            {o.provisional ? (
              <p className="text-[13px] text-muted-foreground">
                Provisional: Google Business Profile not matched; GBP and reviews not scored.
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {o.categories.map((c) => (
            <span
              key={c.key}
              className={`rounded-full border px-2.5 py-0.5 text-[12px] font-semibold ${gradeText(c.grade)}`}
            >
              {c.label} {c.grade}
            </span>
          ))}
        </div>
        <Button
          className="w-fit font-semibold"
          onClick={() => call('openReport', { auditId: audit.id })}
        >
          Generate prospect report (PDF)
        </Button>
      </div>
      <Block title="What’s costing them calls">
        <ol className="flex list-decimal flex-col gap-2.5 pl-5 text-[14px]">
          {o.topIssues.map((i) => (
            <li key={i.title}>
              <p className="font-semibold">{i.title}</p>
              <p className="text-muted-foreground">{i.detail}</p>
            </li>
          ))}
        </ol>
      </Block>
      <Block title="Quick tools">
        <div className="flex flex-wrap gap-2">
          {tools.map((t) => (
            <Button
              key={t.label}
              variant="outline"
              size="sm"
              className="font-semibold"
              nativeButton={false}
              render={<a href={t.href} target="_blank" rel="noreferrer" />}
            >
              {t.label}
            </Button>
          ))}
          <Button
            size="sm"
            className="font-semibold"
            onClick={() => {
              navigator.clipboard
                .writeText(o.summaryText)
                .then(() => toast('Copied'))
                .catch(() => toast('Couldn’t copy'))
            }}
          >
            Copy audit summary
          </Button>
        </div>
      </Block>
      {getEnv().apiMock ? <SendReport audit={audit} /> : null}
    </div>
  )
}
