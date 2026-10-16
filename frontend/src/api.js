const KEY = 'pd_token'

export const getToken = () => {
  try { return localStorage.getItem(KEY) } catch { return null }
}
export const setToken = (t) => {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* storage blocked */ }
}

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

async function request(path, { method = 'GET', body, form, keepalive } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(`/api${path}`, {
    method,
    keepalive,
    headers,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  })
  if (res.status === 401 && path !== '/auth/login') onUnauthorized()
  return res
}

async function json(path, opts) {
  const res = await request(path, opts)
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    const d = data?.detail
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : `HTTP ${res.status}`)
  }
  return data
}

export const api = {
  login: (username, password) => json('/auth/login', { method: 'POST', body: { username, password } }),
  me: () => json('/auth/me'),
  updateMe: (patch) => json('/auth/me', { method: 'PATCH', body: patch }),
  state: () => json('/state'),
  session: () => json('/session', { method: 'POST', body: {} }),
  closeSession: () => request('/session', { method: 'DELETE', keepalive: true }).catch(() => null),
  logout: () => request('/auth/logout', { method: 'POST' }).catch(() => null),
  upload: (file) => {
    const form = new FormData()
    form.append('bib', file)
    return json('/upload', { method: 'POST', form })
  },
  providers: () => json('/providers'),
  open: (site) => json('/open', { method: 'POST', body: site ? { site } : {} }),
  preflight: (site) => json('/preflight', { method: 'POST', body: { site } }),
  verify: (site) => json('/verify', { method: 'POST', body: { site } }),
  dump: (opts) => json('/dump', { method: 'POST', body: opts }),
  start: (opts) => json('/start', { method: 'POST', body: opts }),
  stop: () => json('/stop', { method: 'POST', body: {} }),
  users: () => json('/users'),
  createUser: (u) => json('/users', { method: 'POST', body: u }),
  updateUser: (id, patch) => json(`/users/${id}`, { method: 'PATCH', body: patch }),
  deleteUser: (id) => json(`/users/${id}`, { method: 'DELETE' }),
  async downloadZip() {
    const res = await request('/zip')
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `HTTP ${res.status}`)
    const name = /filename="?([^";]+)"?/.exec(res.headers.get('content-disposition') || '')?.[1] || 'papers.zip'
    const url = URL.createObjectURL(await res.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    a.click()
    URL.revokeObjectURL(url)
  },
}
