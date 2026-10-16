import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'

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
      <div className="card verify">
        {site && check?.busy && <p>Verifying access for <strong>{site}</strong>: opening one article per publisher in the browser below…</p>}
        {site && check?.error && <p className="error">{check.error}</p>}
        {site && check && !check.busy && !check.error && (check.ok
          ? <p className="done">Access verified. Returning to Downloads…</p>
          : <>
              <p className="error">Access is not ready yet:</p>
              <ul>{check.results.filter((r) => r.problem).map((r) => <li key={r.url}>{new URL(r.url).hostname}: {r.problem}</li>)}</ul>
              <p>Solve it in the browser below (open the article, tick the captcha or sign in), then verify again.</p>
            </>)}
        {!site && <p>Sign in or solve any captcha in the browser below, then close this view.</p>}
        <div className="bar">
          {site && check && !check.busy && <button onClick={verify}>Verify again</button>}
          <button onClick={reconnect} disabled={!ready}>Reconnect</button>
          <button onClick={() => back()}>Close remote browser</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {ready && <iframe key={attempt} title="Remote browser" src={SRC} className="remote" />}
    </>
  )
}

export default function Remote() {
  const location = useLocation()
  // Only reachable through the Downloads actions; a typed or bookmarked URL goes home.
  return location.state?.viewer ? <Viewer /> : <Navigate to="/" replace />
}
