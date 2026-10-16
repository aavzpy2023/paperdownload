import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Alert, Button, Card, cls } from '../ui.jsx'

const STATUS = {
  pending: { label: 'Pending', chip: 'border-amber-200 bg-amber-50 text-amber-700', dot: 'bg-amber-500 animate-pulse' },
  running: { label: 'Downloading…', chip: 'border-sky-200 bg-sky-50 text-sky-700', dot: 'bg-sky-500 animate-pulse' },
  done: { label: 'Downloaded', chip: 'border-emerald-200 bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' },
  failed: { label: 'Failed', chip: 'border-rose-200 bg-rose-50 text-rose-700', dot: 'bg-rose-500' },
}

const SOURCE = {
  sciencedirect: { dot: 'bg-emerald-500', chip: 'border-emerald-200 bg-emerald-50 text-emerald-800', icon: 'fa-flask' },
  pubmed: { dot: 'bg-cyan-500', chip: 'border-cyan-200 bg-cyan-50 text-cyan-800', icon: 'fa-book-medical' },
  scopus: { dot: 'bg-orange-500', chip: 'border-orange-200 bg-orange-50 text-orange-800', icon: 'fa-magnifying-glass-chart' },
  wos: { dot: 'bg-purple-500', chip: 'border-purple-200 bg-purple-50 text-purple-800', icon: 'fa-globe' },
  ieee: { dot: 'bg-indigo-500', chip: 'border-indigo-200 bg-indigo-50 text-indigo-800', icon: 'fa-microchip' },
  ebsco: { dot: 'bg-rose-500', chip: 'border-rose-200 bg-rose-50 text-rose-800', icon: 'fa-database' },
  other: { dot: 'bg-slate-500', chip: 'border-slate-200 bg-slate-50 text-slate-700', icon: 'fa-link' },
}
const sourceStyle = (id) => SOURCE[id] || SOURCE.other

const SORTS = { index: '#', title: 'Title', year: 'Year', status: 'Status' }
const PAGE_SIZES = [10, 25, 50, 100]

function Stat({ icon, tone, children }) {
  return (
    <div className={cls('flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium', tone)}>
      <i className={cls('fa-solid', icon)} />
      <span>{children}</span>
    </div>
  )
}

function AccessLabel({ group, verifying }) {
  if (verifying) return <span className="flex items-center gap-1 font-medium text-sky-600"><i className="fa-solid fa-spinner fa-spin" /> Verifying…</span>
  if (group.access === 'ok') return <span className="flex items-center gap-1 font-medium text-emerald-600"><i className="fa-solid fa-check" /> Auth Ready</span>
  if (group.access === 'none') return <span className="font-medium text-slate-500">Not needed</span>
  return <span className="flex items-center gap-1 font-medium text-amber-600"><i className="fa-solid fa-shield-halved" /> Verification required</span>
}

export default function Downloader() {
  const [state, setState] = useState(null)
  const [config, setConfig] = useState({ institution_url: '', providers: [] })
  const [selected, setSelected] = useState(new Set())
  const location = useLocation()
  const [message, setMessage] = useState(location.state?.notice || '')
  const [fileName, setFileName] = useState('')
  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState('index')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
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
  const toRemote = (path = '/browser') => navigate(path, { state: { viewer: true } })

  const rows = useMemo(() => (state?.rows ?? []).map((r, i) => ({ ...r, i })), [state])
  const running = !!state?.running
  const verifying = state?.verifying ?? ''
  const counts = state?.counts ?? { pending: 0, running: 0, done: 0, failed: 0 }
  const total = rows.length
  const percent = total ? Math.round((counts.done / total) * 100) : 0

  const groups = config.providers.map((p) => {
    const mine = rows.filter((r) => r.sources.includes(p.id)).map((r) => r.i)
    // Failed rows stay in the list: they are retried by the same button.
    const pending = mine.filter((i) => rows[i].status !== 'done')
    const failed = pending.filter((i) => rows[i].status === 'failed').length
    const picked = pending.filter((i) => selected.has(i))
    const access = state?.access?.[p.id] ?? 'required'
    return { ...p, access, failed, total: mine.length, pending, indices: picked.length ? picked : pending }
  }).filter((g) => g.total > 0)

  const readySite = (r) => groups.find((g) => r.sources.includes(g.id) && g.access !== 'required')?.id

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const found = rows.filter((r) => !q || [r.title, r.key, r.doi].some((v) => (v || '').toLowerCase().includes(q)))
    const by = { index: (a, b) => a.i - b.i, title: (a, b) => a.title.localeCompare(b.title), year: (a, b) => (b.year || '').localeCompare(a.year || ''), status: (a, b) => a.status.localeCompare(b.status) }
    return [...found].sort(by[sortBy])
  }, [rows, query, sortBy])
  const pages = Math.max(1, Math.ceil(visible.length / pageSize))
  const current = Math.min(page, pages)
  const shown = visible.slice((current - 1) * pageSize, current * pageSize)

  const picked = [...selected].filter((i) => rows[i] && rows[i].status !== 'done')
  const plan = {}
  let waiting = 0
  picked.forEach((i) => {
    const s = readySite(rows[i])
    if (s) (plan[s] ||= []).push(i)
    else waiting += 1
  })
  const ready = Object.values(plan).reduce((n, a) => n + a.length, 0)
  const failedPlan = {}
  rows.filter((r) => r.status === 'failed').forEach((r) => {
    const s = readySite(r)
    if (s) (failedPlan[s] ||= []).push(r.i)
  })
  const retryable = Object.values(failedPlan).reduce((n, a) => n + a.length, 0)
  const retryFailed = () => act(() => api.start({ sites: failedPlan }))
  const downloadSelected = () => act(() => api.start({ sites: plan }), () => (waiting ? `${waiting} selected record(s) were skipped: verify access to their database first.` : ''))

  const upload = () => {
    const f = fileRef.current?.files[0]
    if (f) {
      setFileName(f.name)
      act(() => api.upload(f).then((r) => { setSelected(new Set()); setPage(1); return r }), (r) => `Loaded ${r.count} entries`)
    }
    if (fileRef.current) fileRef.current.value = ''
  }
  const toggle = (i, on) => setSelected((s) => { const n = new Set(s); on ? n.add(i) : n.delete(i); return n })
  const allShownSelected = shown.length > 0 && shown.every((r) => selected.has(r.i))
  const copyPath = () => {
    const text = state?.out_dir || ''
    if (navigator.clipboard) { navigator.clipboard.writeText(text).catch(() => null); return }
    // Plain HTTP on a LAN address is not a secure context: fall back to the old selection trick.
    const box = Object.assign(document.createElement('textarea'), { value: text })
    document.body.appendChild(box)
    box.select()
    document.execCommand('copy')
    box.remove()
  }

  return (
    <>
      <Card className="p-4 sm:p-5">
        <div className="flex flex-col items-stretch justify-between gap-4 lg:flex-row lg:items-center">
          <div className="flex flex-1 flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <label className={cls('group relative flex flex-1 cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 px-4 py-2.5 transition hover:border-sky-500 hover:bg-sky-50/40', running && 'pointer-events-none opacity-50')}>
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 group-hover:text-sky-600"><i className="fa-solid fa-file-arrow-up text-sm" /></div>
              <div className="text-left">
                <p className="text-xs font-medium text-slate-700 group-hover:text-sky-700">Upload BibTeX or PubMed file</p>
                <p className="text-[11px] text-slate-400">Supported formats: .bib, .nbib</p>
              </div>
              <input ref={fileRef} type="file" accept=".bib,.nbib" onChange={upload} disabled={running} className="sr-only" />
            </label>
            {total > 0 && (
              <div className="flex items-center gap-2 self-center rounded-lg border border-slate-200/60 bg-slate-100 px-3 py-2 font-mono text-xs text-slate-500 sm:self-auto">
                <i className="fa-solid fa-file-code text-slate-400" />
                <span className="max-w-[180px] truncate">{fileName || 'loaded.bib'}</span>
                <span className="rounded bg-emerald-50 px-1 font-sans text-[10px] font-semibold text-emerald-600">{total} loaded</span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <Button onClick={() => (config.institution_url ? act(async () => { await api.open(); toRemote() }) : navigate('/settings'))} title={config.institution_url || 'Set your institution or library URL in Settings'}>
              <i className="fa-solid fa-building-columns text-indigo-500" /> {config.institution_url ? 'Open Institution Page' : 'Set Institution URL'}
            </Button>
            <Button kind="warn" onClick={() => act(() => api.stop())} disabled={!running} title="Stops after the current paper; press Download again to resume">
              <i className="fa-solid fa-circle-pause text-amber-600" /> Pause
            </Button>
            <Button kind="primary" onClick={() => act(() => api.downloadZip())} disabled={running || !state?.pdf_count} title={running ? 'Wait for the download to finish' : 'All PDFs of this folder in one .zip'}>
              <i className="fa-solid fa-file-zipper" /> Download All PDFs (.zip)
              <span className="ml-1 rounded-full border border-sky-400 bg-sky-500 px-1.5 text-[10px] font-bold text-white">{state?.pdf_count ?? 0}</span>
            </Button>
          </div>
        </div>
      </Card>

      {(state?.error || message) && <Alert kind={state?.error ? 'error' : 'info'}>{state?.error || message}</Alert>}

      {groups.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-slate-900">
              Source Databases &amp; Access Authentication
              <span className="text-xs font-normal text-slate-500">({groups.length} source{groups.length === 1 ? '' : 's'} identified)</span>
            </h2>
            <span className="hidden items-center gap-1 text-xs text-slate-400 sm:flex"><i className="fa-solid fa-circle-info" /> Open articles → Verify access → Download</span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {groups.map((g) => {
              const style = sourceStyle(g.id)
              const isVerifying = verifying === g.id
              const locked = g.access === 'required'
              const retryOnly = g.failed > 0 && g.failed === g.pending.length
              return (
                <div key={g.id} className={cls('flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm transition hover:border-slate-300', locked && 'ring-1 ring-amber-500/10')}>
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-800"><span className={cls('h-2 w-2 rounded-full', style.dot)} />{g.label}</span>
                      <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium text-slate-700">{g.total} {g.total === 1 ? 'entry' : 'entries'}</span>
                    </div>
                    <div className="mb-4 mt-2 flex items-center justify-between text-xs text-slate-500">
                      <span>
                        Pending: <strong className={cls('font-mono', g.pending.length - g.failed ? 'text-amber-700' : 'text-slate-800')}>{g.pending.length - g.failed}</strong>
                        {g.failed > 0 && <span className="ml-2 text-rose-600">Failed: <strong className="font-mono">{g.failed}</strong></span>}
                      </span>
                      <AccessLabel group={g} verifying={isVerifying} />
                    </div>
                  </div>
                  <div className="space-y-2 border-t border-slate-100 pt-2">
                    <div className="flex gap-1.5">
                      <button type="button" className="flex-1 truncate rounded-lg bg-slate-100 px-2 py-1.5 text-[11px] font-medium text-slate-700 transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50" disabled={running} onClick={() => act(async () => { await api.open(g.id); toRemote() })}>Open {g.label}</button>
                      <button type="button" className="flex-1 truncate rounded-lg bg-sky-50 px-2 py-1.5 text-[11px] font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400" disabled={running || g.access === 'none'} title="Opens one article of your list per publisher" onClick={() => act(async () => { await api.preflight(g.id); toRemote() })}>Open articles</button>
                    </div>
                    <div className="flex gap-1.5">
                      {locked && (
                        <button type="button" className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-amber-100 px-2 py-1.5 text-[11px] font-semibold text-amber-800 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50" disabled={running || !!verifying} onClick={() => toRemote(`/browser?verify=${g.id}`)}>
                          <i className="fa-solid fa-key" /> Verify access
                        </button>
                      )}
                      <button type="button" className={cls('flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold transition disabled:cursor-not-allowed', locked ? 'bg-slate-100 text-slate-400' : 'flex-1 bg-sky-600 text-white hover:bg-sky-700 disabled:bg-slate-100 disabled:text-slate-400')} disabled={running || !g.indices.length || locked} title={locked ? 'Verify access first' : ''} onClick={() => act(() => api.start({ site: g.id, indices: g.indices }))}>
                        <i className={cls('fa-solid', retryOnly ? 'fa-rotate-right' : 'fa-download')} /> {retryOnly ? 'Retry' : 'Download'} ({g.indices.length}{g.indices.length !== g.pending.length ? ' selected' : ''})
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {total > 0 && (
        <Card className="p-4 sm:p-5">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <Stat icon="fa-list-check" tone="border-transparent bg-slate-100 text-slate-700">Loaded: <strong className="font-mono">{total}</strong> entries</Stat>
              <Stat icon="fa-circle-check" tone="border-emerald-200 bg-emerald-50 text-emerald-800">Downloaded: <strong className="font-mono">{counts.done}</strong></Stat>
              <Stat icon="fa-clock" tone="border-amber-200 bg-amber-50 text-amber-800">Pending: <strong className="font-mono">{counts.pending + counts.running}</strong></Stat>
              <Stat icon="fa-triangle-exclamation" tone={counts.failed ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-transparent bg-slate-100 text-slate-500'}>Failed: <strong className="font-mono">{counts.failed}</strong></Stat>
            </div>
            {state?.out_dir && (
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
                <span className="shrink-0 text-slate-400"><i className="fa-regular fa-folder-open" /> Output:</span>
                <code className="max-w-[280px] truncate font-mono text-slate-700 sm:max-w-[360px]" title={state.out_dir}>{state.out_dir}</code>
                <button type="button" className="p-1 text-slate-400 transition hover:text-sky-600" title="Copy output path" onClick={copyPath}><i className="fa-regular fa-copy" /></button>
              </div>
            )}
          </div>
          <div className="mt-4 flex items-center gap-4 border-t border-slate-100 pt-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-gradient-to-r from-sky-500 to-indigo-600 transition-all" style={{ width: `${percent}%` }} />
            </div>
            <span className="font-mono text-xs font-medium text-slate-600">{percent}% Completed ({counts.done}/{total})</span>
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-col justify-between gap-3 border-b border-slate-200 bg-slate-50/50 px-5 py-4 sm:flex-row sm:items-center">
          <div>
            <h3 className="text-base font-bold text-slate-900">Download Queue &amp; Metadata Records</h3>
            <p className="mt-0.5 text-xs text-slate-500">Manage full-text retrieval status and citations</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <input value={query} onChange={(e) => { setQuery(e.target.value); setPage(1) }} placeholder="Filter title, key or DOI…" className="w-44 rounded-lg border-slate-300 bg-white py-1.5 pl-8 pr-3 text-xs focus:border-sky-500 focus:ring-sky-500 sm:w-56" />
              <i className="fa-solid fa-magnifying-glass absolute left-2.5 top-2 text-xs text-slate-400" />
            </div>
            {counts.failed > 0 && (
              <Button kind="warn" onClick={retryFailed} disabled={running || !retryable} title="Try again every failed record whose database is verified">
                <i className="fa-solid fa-rotate-right" /> Retry failed ({retryable})
              </Button>
            )}
            <Button kind="primary" onClick={downloadSelected} disabled={running || !ready} title={selected.size ? (waiting ? `${waiting} selected record(s) need access verified first` : 'Download the selected records') : 'Select records with the checkboxes'}>
              <i className="fa-solid fa-download" /> Download selected ({ready})
            </Button>
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <i className="fa-solid fa-arrow-down-wide-short" />
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="rounded-lg border-slate-300 py-1.5 pl-2 pr-7 text-xs focus:border-sky-500 focus:ring-sky-500">
                {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>Sort: {v}</option>)}
              </select>
            </label>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="w-10 py-3.5 pl-5 pr-3"><input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500" checked={allShownSelected} onChange={(e) => setSelected((s) => { const n = new Set(s); shown.forEach((r) => (e.target.checked ? n.add(r.i) : n.delete(r.i))); return n })} /></th>
                <th className="w-12 px-3 py-3.5 text-center">#</th>
                <th className="min-w-[120px] px-3 py-3.5">Citation Key</th>
                <th className="min-w-[340px] px-4 py-3.5">Paper Title &amp; Details</th>
                <th className="w-20 px-3 py-3.5 text-center">Year</th>
                <th className="w-32 px-4 py-3.5">Source</th>
                <th className="w-32 px-4 py-3.5">Status</th>
                <th className="w-28 py-3.5 pl-3 pr-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-10 text-center text-sm text-slate-400">{total ? 'No records match the filter.' : 'Upload a .bib file to start.'}</td></tr>
              )}
              {shown.map((r) => {
                const st = STATUS[r.status] || STATUS.pending
                const site = readySite(r)
                return (
                  <tr key={r.i} className="group transition hover:bg-slate-50/70">
                    <td className="py-4 pl-5 pr-3 align-top"><input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500" checked={selected.has(r.i)} disabled={running} onChange={(e) => toggle(r.i, e.target.checked)} /></td>
                    <td className="px-3 py-4 text-center align-top font-mono text-xs text-slate-400">{r.i + 1}</td>
                    <td className="px-3 py-4 align-top"><span className="inline-block break-all rounded border border-sky-200/60 bg-sky-50/80 px-2 py-0.5 font-mono text-xs font-semibold text-sky-800">{r.key}</span></td>
                    <td className="px-4 py-4 align-top">
                      <p className="text-sm font-semibold leading-snug text-slate-900">{r.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500">
                        {r.doi && <span><i className="fa-regular fa-id-badge mr-1 text-slate-400" />DOI: {r.doi}</span>}
                        {r.journal && <span>{r.journal}</span>}
                        {r.detail && <span className={r.status === 'failed' ? 'text-rose-600' : r.status === 'done' ? 'text-emerald-600' : ''}>{r.detail}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-4 text-center align-top text-xs font-medium text-slate-600">{r.year}</td>
                    <td className="px-4 py-4 align-top">
                      <div className="flex flex-wrap gap-1">
                        {r.sources.map((s) => (
                          <span key={s} className={cls('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium', sourceStyle(s).chip)}>
                            <i className={cls('fa-solid text-[10px]', sourceStyle(s).icon)} />{s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <span className={cls('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium', st.chip)}><span className={cls('h-1.5 w-1.5 rounded-full', st.dot)} />{st.label}</span>
                    </td>
                    <td className="py-4 pl-3 pr-5 text-right align-top">
                      <button type="button" className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-sky-600 disabled:cursor-not-allowed disabled:opacity-40" disabled={running || r.status === 'done' || !site} title={r.status === 'done' ? 'Already downloaded' : site ? 'Fetch this PDF' : 'Verify access for its database first'} onClick={() => act(() => api.start({ site, indices: [r.i] }))}>
                        <i className="fa-solid fa-cloud-arrow-down text-xs" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col items-center justify-between gap-3 border-t border-slate-200 px-5 py-3 text-xs text-slate-500 sm:flex-row">
          <div className="flex items-center gap-3">
            <span>Showing <strong>{visible.length ? (current - 1) * pageSize + 1 : 0} to {Math.min(current * pageSize, visible.length)}</strong> of {visible.length} records</span>
            <label className="flex items-center gap-1">Per page:
              <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }} className="rounded-lg border-slate-300 py-1 pl-2 pr-7 text-xs focus:border-sky-500 focus:ring-sky-500">
                {PAGE_SIZES.map((n) => <option key={n}>{n}</option>)}
              </select>
            </label>
          </div>
          <div className="flex items-center gap-1.5">
            <Button onClick={() => setPage(current - 1)} disabled={current <= 1} className="px-2.5 py-1">Previous</Button>
            <span className="rounded-lg border border-sky-500 px-2.5 py-1 font-medium text-sky-700">{current} / {pages}</span>
            <Button onClick={() => setPage(current + 1)} disabled={current >= pages} className="px-2.5 py-1">Next</Button>
          </div>
        </div>
      </Card>
    </>
  )
}
