import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { Alert, Button, Card } from '../ui.jsx'

export default function Settings() {
  const { user, setUser } = useAuth()
  const [url, setUrl] = useState(user.institution_url || '')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const save = async (e) => {
    e.preventDefault()
    setMessage('')
    setError('')
    try {
      setUser(await api.updateMe({ institution_url: url.trim() }))
      setMessage('Saved.')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Card className="max-w-xl p-6">
      <form onSubmit={save} className="space-y-4">
        <h2 className="text-base font-bold text-slate-900">Settings</h2>
        <label className="block text-sm font-medium text-slate-700">Institution or library login URL (optional)
          <input type="url" className="mt-1 w-full rounded-lg border-slate-300 text-sm focus:border-sky-500 focus:ring-sky-500" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://library.your-university.edu" />
        </label>
        <p className="text-xs leading-relaxed text-slate-500">
          The page you use to sign in to your university's resources (library portal, EZproxy, OpenAthens…). It is what
          "Open Institution Page" opens. Databases also offer their own "Sign in via your institution" option, which works
          with "Open &lt;database&gt;" without this setting.
        </p>
        {error && <Alert>{error}</Alert>}
        {message && <Alert kind="ok">{message}</Alert>}
        <Button kind="primary" type="submit">Save</Button>
      </form>
    </Card>
  )
}
