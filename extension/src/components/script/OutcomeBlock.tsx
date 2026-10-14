import { useState } from 'react'
import { BookingWidget } from '@/components/script/BookingWidget'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import { useSaveOutcomeMutation } from '@/hooks/queries'
import type { Contact, Outcome } from '@/lib/api/types'

const DEFAULT_NOTES: Record<string, string> = {
  schedule_appointment: 'Appointment scheduled from call',
}

interface OutcomeBlockProps {
  contactId: string
  contact: Contact
  outcomes: Outcome[]
  missing: { fieldKey: string; label: string }[]
  bookingWidgetUrl: string
  onOpenScript: () => void
}

export function OutcomeBlock({
  contactId,
  contact,
  outcomes,
  missing,
  bookingWidgetUrl,
  onOpenScript,
}: OutcomeBlockProps) {
  const [outcomeId, setOutcomeId] = useState('')
  const [note, setNote] = useState('')
  const [bookAnyway, setBookAnyway] = useState(false)
  const [booked, setBooked] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const save = useSaveOutcomeMutation(contactId)

  const selected = outcomes.find((o) => o.id === outcomeId)
  const showGate = selected?.books === true && missing.length > 0 && !bookAnyway
  const showWidget = selected?.books === true && (missing.length === 0 || bookAnyway)

  function select(id: string) {
    setOutcomeId(id)
    setNote(DEFAULT_NOTES[id] ?? '')
    setBookAnyway(false)
    setBooked(false)
    setSaveError(null)
  }

  async function saveOutcome() {
    if (!selected) return
    setSaveError(null)
    try {
      await save.mutateAsync({ outcomeId, note, booked: showWidget && booked })
      toast('Outcome saved')
      setOutcomeId('')
      setNote('')
      setBookAnyway(false)
      setBooked(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save outcome')
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={`${contactId}-outcome`} className="text-xs font-medium">
        How did the call go?
      </Label>
      <Select value={outcomeId} onValueChange={(v) => v && select(v)}>
        <SelectTrigger id={`${contactId}-outcome`} className="w-full">
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent>
          {outcomes.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {showGate ? (
        <Alert className="border-amber-500/40 bg-amber-50 text-amber-900">
          <AlertDescription className="flex flex-col gap-2 text-xs">
            <p className="font-medium">Fill these before booking</p>
            <ul className="list-disc pl-4">
              {missing.map((m) => (
                <li key={m.fieldKey}>{m.label}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button variant="outline" size="xs" onClick={onOpenScript}>
                Open call script
              </Button>
              <Button variant="outline" size="xs" onClick={() => setBookAnyway(true)}>
                Book anyway
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      {showWidget ? (
        <>
          <BookingWidget widgetUrl={bookingWidgetUrl} contact={contact} />
          <Label className="flex cursor-pointer items-center gap-2 text-xs">
            <Checkbox checked={booked} onCheckedChange={(v) => setBooked(v === true)} />
            Appointment booked
          </Label>
        </>
      ) : null}

      {selected ? (
        <>
          <Textarea
            aria-label="Outcome note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note…"
          />
          <Button onClick={saveOutcome} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : `Save outcome: ${selected.label}`}
          </Button>
          {saveError ? (
            <Alert variant="destructive">
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
