import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { Alert, Button, Card } from '../ui.jsx'

const EMPTY = { username: '', password: '', role: 'user' }
const field = 'rounded-lg border-slate-300 text-sm focus:border-sky-500 focus:ring-sky-500'
const ROLES = ['user', 'admin', 'guest']

export default function Users() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')

  const load = useCallback(() => api.users().then(setUsers).catch((e) => setError(e.message)), [])
  useEffect(() => { load() }, [load])

  const run = async (fn) => {
    setError('')
    try { await fn(); await load() } catch (e) { setError(e.message) }
  }

  const create = (e) => {
    e.preventDefault()
    run(async () => { await api.createUser(form); setForm(EMPTY) })
  }
  const resetPassword = (u) => {
    const password = window.prompt(`New password for ${u.username} (min. 6 characters):`)
    if (password) run(() => api.updateUser(u.id, { password }))
  }
  const remove = (u) => {
    if (window.confirm(`Delete user ${u.username}?`)) run(() => api.deleteUser(u.id))
  }

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50/50 px-5 py-4">
        <h2 className="text-base font-bold text-slate-900">User management</h2>
        <p className="mt-0.5 text-xs text-slate-500">Admins and users keep their browser profile; guests get a temporary one.</p>
      </div>
      <div className="space-y-4 p-5">
        {error && <Alert>{error}</Alert>}
        <form className="flex flex-wrap items-center gap-2" onSubmit={create}>
          <input className={field} placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} />
          <input className={field} type="password" placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} autoComplete="new-password" />
          <select className={field} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
          <Button kind="primary" type="submit"><i className="fa-solid fa-user-plus" /> Add user</Button>
        </form>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="px-3 py-3">Username</th><th className="px-3 py-3">Role</th><th className="px-3 py-3">Active</th><th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => {
                const self = u.id === me.id
                return (
                  <tr key={u.id} className="hover:bg-slate-50/70">
                    <td className="px-3 py-3 font-medium text-slate-900">{u.username}{self && <span className="ml-2 text-xs text-slate-400">(you)</span>}</td>
                    <td className="px-3 py-3">
                      <select className={field} value={u.role} onChange={(e) => run(() => api.updateUser(u.id, { role: e.target.value }))}>
                        {ROLES.map((r) => <option key={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500" checked={u.active} disabled={self} onChange={(e) => run(() => api.updateUser(u.id, { active: e.target.checked }))} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex justify-end gap-2">
                        <Button onClick={() => resetPassword(u)}>Reset password</Button>
                        <Button onClick={() => remove(u)} disabled={self}>Delete</Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  )
}
