import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginScreen } from '@/components/panel/LoginScreen'
import { ApiError } from '@/lib/api/errors'

const loginMock = vi.fn()

vi.mock('@/hooks/use-auth', () => ({
  login: (...args: unknown[]) => loginMock(...args),
}))

vi.mock('@/hooks/use-theme', () => ({
  useTheme: () => ({ theme: 'light', isDark: false, toggle: () => {} }),
}))

describe('LoginScreen', () => {
  beforeEach(() => {
    loginMock.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('signs in with email and password', async () => {
    loginMock.mockResolvedValueOnce({ id: 'u1' })
    render(<LoginScreen />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'sdr@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() =>
      expect(loginMock).toHaveBeenCalledWith('sdr@example.com', 'demo', undefined),
    )
  })

  it('shows the totp field after totp_required and retries with the code', async () => {
    loginMock
      .mockRejectedValueOnce(new ApiError(401, 'totp_required', 'Two-factor code required'))
      .mockResolvedValueOnce({ id: 'u1' })
    render(<LoginScreen />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'sdr@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'totp' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByLabelText('6-digit code')).toBeDefined())
    fireEvent.change(screen.getByLabelText('6-digit code'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() =>
      expect(loginMock).toHaveBeenLastCalledWith('sdr@example.com', 'totp', '123456'),
    )
  })

  it('shows a form error on invalid credentials', async () => {
    loginMock.mockRejectedValueOnce(
      new ApiError(401, 'invalid_credentials', 'Invalid email or password'),
    )
    render(<LoginScreen />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'sdr@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Invalid email or password')).toBeDefined())
  })
})
