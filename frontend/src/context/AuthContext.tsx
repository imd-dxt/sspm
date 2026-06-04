import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'

interface AuthState {
  token: string | null
  username: string | null
}

interface AuthContextValue extends AuthState {
  login: (token: string, username: string) => void
  logout: () => void
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredAuth(): AuthState {
  return {
    token: localStorage.getItem('sspm_token'),
    username: localStorage.getItem('sspm_username'),
  }
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [auth, setAuth] = useState<AuthState>(readStoredAuth)

  const login = useCallback((token: string, username: string) => {
    localStorage.setItem('sspm_token', token)
    localStorage.setItem('sspm_username', username)
    setAuth({ token, username })
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('sspm_token')
    localStorage.removeItem('sspm_username')
    setAuth({ token: null, username: null })
  }, [])

  // Listen for 401s dispatched from the API client. This avoids a hard
  // window.location redirect, which would wipe the SPA mid-login.
  useEffect(() => {
    function handleAuthLogout() {
      console.warn('[Auth] Received 401 → clearing session')
      localStorage.removeItem('sspm_token')
      localStorage.removeItem('sspm_username')
      setAuth({ token: null, username: null })
    }
    window.addEventListener('auth:logout', handleAuthLogout)
    return () => window.removeEventListener('auth:logout', handleAuthLogout)
  }, [])

  return (
    <AuthContext.Provider value={{ ...auth, login, logout, isAuthenticated: !!auth.token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
