import { useState } from 'react'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login } from '@/hooks/use-auth'
import { ApiError } from '@/lib/api/errors'
import { getEnv } from '@/lib/env'
import { call } from '@/lib/messaging'

export function LoginScreen() {
  return getEnv().apiMock ? <MockLoginScreen /> : <WebLoginScreen />
}

function WebLoginScreen() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    setPending(true)
    setError(null)
    try {
      await call('connectWeb')
    } catch {
      setError('Could not open WCM sign-in. Try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader />
      <main className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-xl font-semibold">Connect your WCM account</h1>
        <p className="text-sm text-muted-foreground dark:text-white">
          Sign in on the WCM website. The extension will connect after sign-in.
        </p>
        <Button onClick={connect} disabled={pending} className="font-semibold dark:text-white">
          {pending ? 'Opening WCM…' : 'Continue with WCM'}
        </Button>
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </main>
    </div>
  )
}

function MockLoginScreen() {
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
