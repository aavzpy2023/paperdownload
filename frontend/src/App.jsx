import { Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth.jsx'
import Downloader from './pages/Downloader.jsx'
import Remote from './pages/Remote.jsx'
import Login from './pages/Login.jsx'
import Settings from './pages/Settings.jsx'
import Users from './pages/Users.jsx'

function Layout() {
  const { user, logout } = useAuth()
  return (
    <>
      <header className="topbar">
        <strong>Paper Downloader</strong>
        <nav>
          <NavLink to="/" end>Downloads</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          {user.role === 'admin' && <NavLink to="/users">Users</NavLink>}
        </nav>
        <span className="spacer" />
        <span>{user.username} ({user.role}){user.role === 'guest' && ' · temporary session'}</span>
        <button onClick={logout}>Sign out</button>
      </header>
      <main><Outlet /></main>
    </>
  )
}

function Protected({ admin = false }) {
  const { user, loading } = useAuth()
  if (loading) return <p className="center">Loading…</p>
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return <Outlet />
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route element={<Protected />}>
        <Route element={<Layout />}>
          <Route index element={<Downloader />} />
          <Route path="browser" element={<Remote />} />
          <Route path="settings" element={<Settings />} />
          <Route element={<Protected admin />}>
            <Route path="users" element={<Users />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
