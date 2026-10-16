import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'

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
    <form className="card settings" onSubmit={save}>
      <h2>Settings</h2>
      <label>Institution or library login URL (optional)
        <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://library.your-university.edu" />
      </label>
      <p className="hint">
        The page you use to sign in to your university's resources (library portal, EZproxy, OpenAthens…). It is what
        "Open my institution page" opens. Databases also offer their own "Sign in via your institution" option, which works
        with "Open &lt;database&gt;" without this setting.
      </p>
      {error && <p className="error">{error}</p>}
      {message && <p className="done">{message}</p>}
      <button type="submit">Save</button>
    </form>
  )
}
