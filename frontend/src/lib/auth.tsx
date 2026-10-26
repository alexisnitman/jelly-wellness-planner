import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import type { RegisterInput, User } from '../types'
import * as api from '../api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState | null>(null)

// "Remembered until log out" comes from the server's httpOnly session cookie: on load we ask the server who we
// are. Nothing about the login, the profile or the calendar is kept in localStorage.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .fetchMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (u: string, p: string) => setUser(await api.login(u, p)), [])
  const register = useCallback(async (i: RegisterInput) => setUser(await api.register(i)), [])
  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }, [])

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside AuthProvider')
  return v
}
