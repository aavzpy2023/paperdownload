import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { Alert, Button, Card, PasswordNote } from '../ui.jsx'

const SRC = '/vnc/vnc.html?autoconnect=1&resize=scale&path=vnc/websockify'
const PING_MS = 2 * 60 * 1000

function Viewer() {
  const [params] = useSearchParams()
  const site = params.get('verify')
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const [check, setCheck] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const started = useRef(false)
  const navigate = useNavigate()
  const { user } = useAuth()

  const back = (state) => navigate('/', { replace: true, state })

  // The remote view only exists while this page is open: it is closed again on leaving.
  useEffect(() => {
    let alive = true
    api.session().then(() => alive && setReady(true)).catch((e) => alive && setError(e.message))
    const ping = setInterval(() => api.session().catch(() => null), PING_MS)
    return () => { alive = false; clearInterval(ping); api.closeSession() }
  }, [])

  const reconnect = () => {
    setError('')
    api.session().then(() => setAttempt((n) => n + 1)).catch((e) => setError(e.message))
  }

  const verify = async () => {
    setCheck({ busy: true })
    try { setCheck({ busy: false, ...(await api.verify(site)) }) } catch (e) { setCheck({ busy: false, error: e.message }) }
  }

  useEffect(() => {
    if (!check?.ok) return undefined
    const timer = setTimeout(() => back({ notice: `${site}: access verified, you can download.` }), 2000)
    return () => clearTimeout(timer)
  }, [check, site])

  useEffect(() => {
    if (ready && site && !started.current) { started.current = true; verify() }
  }, [ready, site])

  return (
    <>
      <Card className="space-y-3 p-4 sm:p-5">
        {site && check?.busy && <p className="text-sm text-slate-700"><i className="fa-solid fa-spinner fa-spin mr-2 text-sky-600" />Verifying…</p>}
        {site && check?.error && <Alert>{check.error}</Alert>}
        {site && check && !check.busy && !check.error && (check.ok
          ? <Alert kind="ok">Access verified. Returning to Downloads…</Alert>
          : <div className="space-y-2">
              <Alert>Access is not ready yet.</Alert>
              <ul className="list-inside list-disc text-sm text-slate-700">
                {check.results.filter((r) => r.problem).map((r) => <li key={r.url}>{new URL(r.url).hostname}: {r.problem}</li>)}
              </ul>
              <p className="text-sm text-slate-600">Solve it in the browser below (open the article, tick the captcha or sign in), then verify again.</p>
            </div>)}
        {!site && <p className="text-sm text-slate-700">Sign in or solve any captcha in the browser below, then close this view.</p>}
        <PasswordNote guest={user.role === 'guest'} />
        <div className="flex flex-wrap items-center gap-2">
          {site && check && !check.busy && <Button kind="primary" onClick={verify}><i className="fa-solid fa-key" /> Verify again</Button>}
          <Button onClick={reconnect} disabled={!ready || check?.busy}><i className="fa-solid fa-plug" /> Reconnect</Button>
          <Button onClick={() => back()} title={check?.busy ? 'The verification keeps running; Downloads shows the result' : ''}>Close remote browser</Button>
        </div>
      </Card>
      {error && <Alert>{error}</Alert>}
      {ready && <iframe key={attempt} title="Remote browser" src={SRC} className="h-[75vh] w-full rounded-2xl border border-slate-200 bg-black" />}
    </>
  )
}

export default function Remote() {
  const location = useLocation()
  // Only reachable through the Downloads actions; a typed or bookmarked URL goes home.
  return location.state?.viewer ? <Viewer /> : <Navigate to="/" replace />
}
