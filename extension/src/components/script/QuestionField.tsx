import { useState } from 'react'
import { FieldStatus } from '@/components/script/FieldStatus'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { FieldValue, Question } from '@/lib/api/types'
import { formatCurrency } from '@/lib/time'
import { type InputClass, useAutosaveStore } from '@/stores/autosave-store'

interface QuestionFieldProps {
  contactId: string
  block: Question
  initialValue: FieldValue | undefined
}

function inputClassFor(block: Question): InputClass {
  return block.input === 'select' || block.input === 'radio' || block.input === 'checkbox_group'
    ? 'fast'
    : 'slow'
}

function toText(value: FieldValue | undefined): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

export function QuestionField({ contactId, block, initialValue }: QuestionFieldProps) {
  const id = `${contactId}-${block.id}`
  const setField = useAutosaveStore((st) => st.setField)
  const retry = useAutosaveStore((st) => st.retry)
  const status = useAutosaveStore((st) => st.status[contactId]?.[block.fieldKey] ?? 'idle')
  const saveError = useAutosaveStore((st) => st.errors[contactId]?.[block.fieldKey])
  const inputClass = inputClassFor(block)
  const [draft, setDraft] = useState<FieldValue | undefined>(initialValue)
  const [text, setText] = useState(() => toText(initialValue))
  const [numberError, setNumberError] = useState(false)

  function commit(value: FieldValue) {
    setDraft(value)
    setField(contactId, block.fieldKey, value, inputClass)
  }

  function commitText(raw: string) {
    setText(raw)
    commit(raw.trim() ? raw : null)
  }

  function commitNumeric(raw: string) {
    setText(raw)
    if (raw.trim() === '') {
      setNumberError(false)
      commit(null)
      return
    }
    const parsed = Number(raw.replace(/[$,]/g, ''))
    if (!Number.isFinite(parsed) || parsed < 0) {
      setNumberError(true)
      return
    }
    setNumberError(false)
    commit(parsed)
  }

  let input: React.ReactNode
  if (block.input === 'textarea') {
    input = <Textarea id={id} value={text} onChange={(e) => commitText(e.target.value)} />
  } else if (block.input === 'number' || block.input === 'currency') {
    input = (
      <>
        <Input
          id={id}
          inputMode="numeric"
          value={text}
          aria-invalid={numberError}
          onChange={(e) => commitNumeric(e.target.value)}
          onBlur={() => {
            const parsed = Number(text.replace(/[$,]/g, ''))
            if (block.input === 'currency' && text.trim() !== '' && Number.isFinite(parsed)) {
              setText(formatCurrency(parsed))
            }
          }}
        />
        {numberError ? <p className="text-[11px] text-destructive">Enter a number</p> : null}
      </>
    )
  } else if (block.input === 'select') {
    const current = typeof draft === 'string' ? draft : ''
    input = (
      <Select value={current} onValueChange={(v) => commit(v === '' ? null : v)}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent>
          {(block.options ?? []).map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  } else if (block.input === 'radio') {
    const current = typeof draft === 'string' ? draft : ''
    input = (
      <RadioGroup value={current} onValueChange={(v) => commit(v)}>
        {(block.options ?? []).map((o) => (
          <Label key={o.value} className="flex cursor-pointer items-center gap-2 text-xs">
            <RadioGroupItem value={o.value} />
            {o.label}
          </Label>
        ))}
      </RadioGroup>
    )
  } else if (block.input === 'checkbox_group') {
    const current = Array.isArray(draft) ? draft : []
    input = (
      <div className="flex flex-col gap-1.5">
        {(block.options ?? []).map((o) => {
          const checked = current.includes(o.value)
          return (
            <Label key={o.value} className="flex cursor-pointer items-center gap-2 text-xs">
              <Checkbox
                checked={checked}
                onCheckedChange={(v) => {
                  commit(v === true ? [...current, o.value] : current.filter((x) => x !== o.value))
                }}
              />
              {o.label}
            </Label>
          )
        })}
      </div>
    )
  } else {
    input = <Input id={id} value={text} onChange={(e) => commitText(e.target.value)} />
  }

  return (
    <div className="flex flex-col gap-1" data-field={block.fieldKey}>
      <Label htmlFor={id} className="text-xs font-medium">
        {block.label}
      </Label>
      {block.help ? <p className="text-[11px] text-muted-foreground">{block.help}</p> : null}
      {input}
      <FieldStatus
        status={status}
        error={saveError}
        onRetry={() => retry(contactId, block.fieldKey)}
      />
    </div>
  )
}
