import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'

const LABEL = { pending: 'Pending', running: 'Downloading…', done: 'Downloaded', failed: 'Failed' }

export default function Downloader() {
  const [state, setState] = useState(null)
  const [config, setConfig] = useState({ institution_url: '', providers: [] })
  const [selected, setSelected] = useState(new Set())
  const location = useLocation()
  const [message, setMessage] = useState(location.state?.notice || '')
  const fileRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => { api.providers().then(setConfig).catch((e) => setMessage(e.message)) }, [])

  useEffect(() => {
    let alive = true
    let timer
    const poll = async () => {
      try { const s = await api.state(); if (alive) setState(s) } catch { /* 401 is handled globally */ }
      if (alive) timer = setTimeout(poll, 1000)
    }
    poll()
    return () => { alive = false; clearTimeout(timer) }
  }, [])

  const act = async (fn, ok) => {
    setMessage('')
    try { const r = await fn(); setMessage(typeof ok === 'function' ? ok(r) : ok || '') } catch (e) { setMessage(e.message) }
  }

  const rows = state?.rows ?? []
  const running = !!state?.running
  const counts = state?.counts ?? { pending: 0, running: 0, done: 0, failed: 0 }

  const groups = config.providers.map((p) => {
    const mine = rows.flatMap((r, i) => (r.sources.includes(p.id) ? [i] : []))
    const pending = mine.filter((i) => rows[i].status !== 'done')
    const picked = pending.filter((i) => selected.has(i))
    const access = state?.access?.[p.id] ?? 'required'
    return { ...p, access, total: mine.length, pending, indices: picked.length ? picked : pending }
  }).filter((g) => g.total > 0)

  const openBrowser = (site, label) => act(async () => {
    await api.open(site)
    navigate('/browser', { state: { viewer: true } })
  }, `${label} opened`)

  const checkAccess = (site) => act(async () => {
    const r = await api.preflight(site)
    navigate('/browser', { state: { viewer: true } })
    return r
  }, (r) => `${r.urls.length} article(s) opened, one per publisher: solve any captcha or sign-in in each tab, then press Download.`)

  const upload = () => {
    const f = fileRef.current?.files[0]
    if (f) act(() => api.upload(f).then((r) => { setSelected(new Set()); return r }), (r) => `Loaded ${r.count} entries`)
    if (fileRef.current) fileRef.current.value = ''
  }
  const toggle = (i, on) => setSelected((s) => { const n = new Set(s); on ? n.add(i) : n.delete(i); return n })

  return (
    <>
      <div className="bar">
        <input type="file" accept=".bib" ref={fileRef} onChange={upload} disabled={running} />
        <button onClick={() => openBrowser(undefined, 'Browser')} disabled={!config.institution_url} title={config.institution_url || 'Set your institution or library URL in Settings'}>Open my institution page</button>
        {!config.institution_url && <Link to="/settings">Set your institution URL</Link>}
        <button onClick={() => act(() => api.stop())} disabled={!running}>Stop</button>
        <button onClick={() => act(() => api.downloadZip())} disabled={running || !state?.pdf_count} title={running ? 'Wait for the download to finish' : 'All PDFs of this folder in one .zip'}>
          Download all PDFs (.zip) ({state?.pdf_count ?? 0})
        </button>
      </div>

      {groups.length > 0 && (
        <table className="groups">
          <thead><tr><th>Database</th><th>Entries</th><th>Pending</th><th>1. Open articles</th><th>2. Access</th><th>3. Download</th></tr></thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id}>
                <td>{g.label}</td>
                <td>{g.total}</td>
                <td>{g.pending.length}</td>
                <td>
                  <button onClick={() => openBrowser(g.id, g.label)} disabled={running}>Open {g.label}</button>{' '}
                  <button onClick={() => checkAccess(g.id)} disabled={running || g.access === 'none'} title="Opens one article of your list per publisher so you can solve captchas and sign-ins">Open articles</button>
                </td>
                <td>
                  {g.access === 'ok' && <span className="done">Verified</span>}
                  {g.access === 'none' && <span className="pending">Not needed</span>}
                  {g.access === 'required' && <button onClick={() => navigate(`/browser?verify=${g.id}`, { state: { viewer: true } })} disabled={running}>Verify access</button>}
                </td>
                <td>
                  <button onClick={() => act(() => api.start({ site: g.id, indices: g.indices }))} disabled={running || !g.indices.length || g.access === 'required'} title={g.access === 'required' ? 'Verify access first' : ''}>
                    Download ({g.indices.length}{g.indices.length !== g.pending.length ? ' selected' : ''})
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(state?.error || message) && <p className="error">{state?.error || message}</p>}
      <p className="counts">
        <span className="done">Downloaded: {counts.done}</span>
        <span className="pending">Pending: {counts.pending + counts.running}</span>
        <span className="failed">Failed: {counts.failed}</span>
      </p>
      {state && <p>Output folder: {state.out_dir}</p>}
      <table>
        <thead>
          <tr>
            <th><input type="checkbox" checked={rows.length > 0 && selected.size === rows.length} onChange={(e) => setSelected(new Set(e.target.checked ? rows.map((_, i) => i) : []))} /></th>
            <th>#</th><th>Key</th><th>Title</th><th>Year</th><th>Sources</th><th>Status</th><th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={r.status}>
              <td><input type="checkbox" checked={selected.has(i)} disabled={running} onChange={(e) => toggle(i, e.target.checked)} /></td>
              <td>{i + 1}</td><td>{r.key}</td><td>{r.title}</td><td>{r.year}</td><td>{r.sources.join(', ')}</td><td>{LABEL[r.status]}</td><td>{r.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
