import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, hasTokens, setTokens } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!hasTokens()) { setReady(true); return }
    api('/auth/me/').then(setUser).catch(() => setTokens(null)).finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('claimlens:logout', onLogout)
    return () => window.removeEventListener('claimlens:logout', onLogout)
  }, [])

  const login = useCallback(async (username, password) => {
    const data = await api('/auth/login/', { method: 'POST', body: { username, password } })
    setTokens({ access: data.access, refresh: data.refresh })
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    setTokens(null)
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)

export const APPROVER_ROLES = ['MANAGER', 'DEPT_HEAD', 'HR', 'FINANCE', 'ADMIN']
export const OVERSIGHT_ROLES = ['FINANCE', 'ADMIN', 'HR']
export const is = (user, ...roles) => Boolean(user && roles.flat().includes(user.role))
