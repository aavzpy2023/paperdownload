import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!getToken())

  const clear = () => { setToken(null); setUser(null) }
  const logout = async () => { await api.logout(); clear() }

  useEffect(() => {
    setUnauthorizedHandler(clear)
    if (!getToken()) return
    api.me().then(setUser).catch(clear).finally(() => setLoading(false))
  }, [])

  const login = async (username, password) => {
    const { token, user } = await api.login(username, password)
    setToken(token)
    setUser(user)
  }

  return <AuthContext.Provider value={{ user, setUser, loading, login, logout }}>{children}</AuthContext.Provider>
}
