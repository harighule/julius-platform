import { useState, useEffect, useCallback } from 'react'
import { auth } from '../lib/api'

export interface AuthUser {
  id: number
  username: string
  role: string
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem('julius_token')))
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  const normalizeUser = (raw: Record<string, unknown>): AuthUser => ({
    id: (raw.id ?? raw.user_id) as number,
    username: raw.username as string,
    role: raw.role as string,
  })

  useEffect(() => {
    const token = localStorage.getItem('julius_token')
    if (token) {
      auth.me()
        .then(u => { setUser(normalizeUser(u)); setIsAuthenticated(true) })
        .catch(() => { localStorage.removeItem('julius_token'); setIsAuthenticated(false) })
        .finally(() => setLoading(false))
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await auth.login(username, password)
    if (res.requires_mfa) throw new Error('MFA not supported in UI yet')
    localStorage.setItem('julius_token', res.token)
    setUser(normalizeUser(res.user as Record<string, unknown>))
    setIsAuthenticated(true)
    return res
  }, [])

  const logout = useCallback(() => {
    auth.logout().catch(() => {})
    localStorage.removeItem('julius_token')
    setUser(null)
    setIsAuthenticated(false)
  }, [])

  return { user, loading, isAuthenticated, login, logout }
}
