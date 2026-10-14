import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OutcomeBlock } from '@/components/script/OutcomeBlock'
import type { Contact, Outcome } from '@/lib/api/types'

const mutateAsync = vi.fn()

vi.mock('@/hooks/queries', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/hooks/queries')>()
  return { ...mod, useSaveOutcomeMutation: () => ({ mutateAsync, isPending: false }) }
})

vi.mock('@/components/ui/toast', () => ({
  toast: vi.fn(),
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const contact: Contact = {
  id: 'c1',
  firstName: 'M',
  lastName: 'R',
  companyName: 'Glow',
  email: 'm@x.com',
  phone: '123',
  city: 'Austin',
  state: 'TX',
  postalCode: '',
  website: '',
  tags: [],
}

const outcomes: Outcome[] = [
  { id: 'schedule_appointment', label: 'Schedule Appointment', books: true },
  { id: 'callback_requested', label: 'Callback Requested', books: false },
]

describe('OutcomeBlock', () => {
  afterEach(() => {
    cleanup()
    mutateAsync.mockReset()
  })

  it('gates booking behind missing fields', async () => {
    mutateAsync.mockResolvedValueOnce({ noteId: 'n1', tag: 'schedule_appointment' })
    render(
      <OutcomeBlock
        contactId="c1"
        contact={contact}
        outcomes={outcomes}
        missing={[{ fieldKey: 'contact.goal_new_patients', label: 'Goal' }]}
        bookingWidgetUrl="about:blank"
        onOpenScript={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('combobox'))
    fireEvent.click(await screen.findByRole('option', { name: 'Schedule Appointment' }))
    expect(screen.getByText('Fill these before booking')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Book anyway' }))
    expect(screen.getByText('Booking widget (mock)')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Save outcome: Schedule Appointment' }))
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        outcomeId: 'schedule_appointment',
        note: 'Appointment scheduled from call',
        booked: false,
      }),
    )
  })

  it('shows the widget directly when nothing is missing', async () => {
    render(
      <OutcomeBlock
        contactId="c1"
        contact={contact}
        outcomes={outcomes}
        missing={[]}
        bookingWidgetUrl="about:blank"
        onOpenScript={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('combobox'))
    fireEvent.click(await screen.findByRole('option', { name: 'Schedule Appointment' }))
    expect(screen.getByText('Booking widget (mock)')).toBeDefined()
    expect(screen.queryByText('Fill these before booking')).toBeNull()
  })
})
