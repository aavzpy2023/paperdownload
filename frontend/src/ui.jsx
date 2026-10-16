export const btn = {
  base: 'inline-flex items-center justify-center gap-1.5 rounded-xl text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
  outline: 'border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:bg-slate-50',
  primary: 'bg-sky-600 px-4 py-2 font-semibold text-white shadow-sm shadow-sky-600/25 hover:bg-sky-700 active:bg-sky-800',
  warn: 'border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800 hover:bg-amber-100',
  soft: 'bg-slate-100 px-2 py-1.5 text-[11px] text-slate-700 hover:bg-slate-200',
}

export const cls = (...parts) => parts.filter(Boolean).join(' ')

export function Button({ kind = 'outline', className, ...props }) {
  return <button type="button" className={cls(btn.base, btn[kind], className)} {...props} />
}

export function Card({ className, children }) {
  return <section className={cls('rounded-2xl border border-slate-200/90 bg-white shadow-sm', className)}>{children}</section>
}

export function Alert({ kind = 'error', children }) {
  const tone = {
    error: 'border-rose-200 bg-rose-50 text-rose-800',
    ok: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    info: 'border-sky-200 bg-sky-50 text-sky-800',
  }[kind]
  return <p className={cls('rounded-xl border px-4 py-2.5 text-sm', tone)}>{children}</p>
}

export function PasswordNote({ guest = false }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
      <i className="fa-solid fa-lock mt-0.5 text-slate-400" />
      <span>
        Your institution and publisher passwords are <strong>never saved</strong>: Chrome's password manager is disabled here.
        {guest
          ? ' This temporary session, its cookies and its downloads are erased when you sign out.'
          : ' Only the login session (cookies) stays in your browser profile, so you do not have to sign in every time.'}
      </span>
    </p>
  )
}

export function Logo() {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 text-white shadow-md shadow-sky-600/20">
      <i className="fa-solid fa-graduation-cap text-lg" />
    </div>
  )
}
