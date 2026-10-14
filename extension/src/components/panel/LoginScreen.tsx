import { useState } from 'react'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login } from '@/hooks/use-auth'
import { ApiError } from '@/lib/api/errors'

export function LoginScreen() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [totpRequired, setTotpRequired] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [codeError, setCodeError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    setFormError(null)
    setCodeError(null)
    try {
      await login(email, password, totpRequired ? totpCode : undefined)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'totp_required') {
        setTotpRequired(true)
      } else if (err instanceof ApiError && err.code === 'invalid_totp') {
        setTotpRequired(true)
        setCodeError(err.message)
      } else if (err instanceof ApiError && err.code === 'invalid_credentials') {
        setFormError(err.message)
      } else if (err instanceof ApiError && err.code === 'network_error') {
        setFormError("You're offline")
      } else {
        setFormError(err instanceof Error ? err.message : 'Sign in failed')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader />
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-3/4">
          <h1 className="text-center text-xl font-semibold">Sign in</h1>
          <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="login-password">Password</Label>
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {totpRequired ? (
              <div className="flex flex-col gap-1">
                <Label htmlFor="login-totp">6-digit code</Label>
                <Input
                  id="login-totp"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  required
                />
                {codeError ? (
                  <Alert variant="destructive">
                    <AlertDescription>{codeError}</AlertDescription>
                  </Alert>
                ) : null}
              </div>
            ) : null}
            {formError ? (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit" size="lg" className="w-full" disabled={pending}>
              {pending ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </div>
      </main>
    </div>
  )
}
