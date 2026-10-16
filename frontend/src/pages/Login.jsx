import { useState } from 'react'
import { useAuth } from '../auth.jsx'
import { Alert, Button, Card, Logo, PasswordNote } from '../ui.jsx'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <Card className="w-full max-w-sm p-8">
        <form onSubmit={submit} className="space-y-5">
          <div className="flex flex-col items-center gap-3">
            <Logo />
            <div className="text-center">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">Paper Downloader</h1>
              <p className="text-xs text-slate-500">Automated Academic Literature Retrieval</p>
            </div>
          </div>
          <label className="block text-sm font-medium text-slate-700">Username
            <input className="mt-1 w-full rounded-lg border-slate-300 text-sm focus:border-sky-500 focus:ring-sky-500" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" required />
          </label>
          <label className="block text-sm font-medium text-slate-700">Password
            <input className="mt-1 w-full rounded-lg border-slate-300 text-sm focus:border-sky-500 focus:ring-sky-500" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <Alert>{error}</Alert>}
          <Button kind="primary" type="submit" className="w-full py-2.5 text-sm" disabled={busy}>Sign in</Button>
          <PasswordNote />
        </form>
      </Card>
    </div>
  )
}
