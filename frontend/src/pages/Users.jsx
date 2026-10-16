import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'

const EMPTY = { username: '', password: '', role: 'user' }

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
    <>
      <h2>User management</h2>
      {error && <p className="error">{error}</p>}
      <form className="bar" onSubmit={create}>
        <input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} />
        <input type="password" placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} autoComplete="new-password" />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="user">user</option>
          <option value="admin">admin</option>
          <option value="guest">guest</option>
        </select>
        <button type="submit">Add user</button>
      </form>
      <table>
        <thead><tr><th>Username</th><th>Role</th><th>Active</th><th /></tr></thead>
        <tbody>
          {users.map((u) => {
            const self = u.id === me.id
            return (
              <tr key={u.id}>
                <td>{u.username}{self && ' (you)'}</td>
                <td>
                  <select value={u.role} onChange={(e) => run(() => api.updateUser(u.id, { role: e.target.value }))}>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                    <option value="guest">guest</option>
                  </select>
                </td>
                <td>
                  <input type="checkbox" checked={u.active} disabled={self} onChange={(e) => run(() => api.updateUser(u.id, { active: e.target.checked }))} />
                </td>
                <td className="actions">
                  <button onClick={() => resetPassword(u)}>Reset password</button>
                  <button onClick={() => remove(u)} disabled={self}>Delete</button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </>
  )
}
