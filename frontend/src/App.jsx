import { Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth.jsx'
import Downloader from './pages/Downloader.jsx'
import Login from './pages/Login.jsx'
import Remote from './pages/Remote.jsx'
import Settings from './pages/Settings.jsx'
import Users from './pages/Users.jsx'
import { Button, Logo, cls } from './ui.jsx'

const navClass = ({ isActive }) => cls(
  'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition',
  isActive ? 'border border-sky-100/60 bg-sky-50 font-semibold text-sky-700' : 'font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900',
)

function Layout() {
  const { user, logout } = useAuth()
  const hasInstitution = !!user.institution_url
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <Logo />
              <div>
                <span className="text-lg font-bold tracking-tight text-slate-900">Paper Downloader</span>
                <p className="hidden text-xs text-slate-500 sm:block">Automated Academic Literature Retrieval</p>
              </div>
            </div>
            <nav className="hidden space-x-1 md:flex" aria-label="Main">
              <NavLink to="/" end className={navClass}><i className="fa-solid fa-cloud-arrow-down" /> Downloads</NavLink>
              <NavLink to="/settings" className={navClass}><i className="fa-solid fa-sliders" /> Settings</NavLink>
              {user.role === 'admin' && <NavLink to="/users" className={navClass}><i className="fa-solid fa-users" /> Users</NavLink>}
            </nav>
          </div>
          <div className="flex items-center gap-3 sm:gap-4">
            <NavLink
              to="/settings"
              className={cls(
                'hidden items-center gap-2 rounded-full border px-2.5 py-1.5 text-xs font-medium xl:flex',
                hasInstitution ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700',
              )}
            >
              <span className={cls('h-2 w-2 rounded-full', hasInstitution ? 'bg-emerald-500' : 'bg-amber-500')} />
              {hasInstitution ? 'Institution page set' : 'No institution URL'}
            </NavLink>
            <div className="flex items-center gap-3 border-slate-200 pl-2 sm:border-l">
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-300 bg-slate-200 text-xs font-semibold text-slate-600">
                {user.username.slice(0, 2).toUpperCase()}
              </div>
              <div className="hidden text-left lg:block">
                <p className="text-xs font-medium leading-tight text-slate-800">{user.username} ({user.role})</p>
                <p className="text-[11px] text-slate-500">{user.role === 'guest' ? 'Temporary session' : `Account #${user.id}`}</p>
              </div>
              <Button onClick={logout}><i className="fa-solid fa-right-from-bracket text-slate-400" /> Sign out</Button>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-6 sm:px-6 lg:px-8"><Outlet /></main>
    </div>
  )
}

function Protected({ admin = false }) {
  const { user, loading } = useAuth()
  if (loading) return <p className="mt-[20vh] text-center text-slate-500">Loading…</p>
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
