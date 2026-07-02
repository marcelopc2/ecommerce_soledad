import { createContext, useContext, useState, useEffect } from 'react'
import { api } from './api'

const AuthContext = createContext(null)

const ACCESS = 'ib_access'
const REFRESH = 'ib_refresh'

// Inyecta el token en cada request y refresca automáticamente en 401.
export function setupAuthInterceptors(onLogout) {
  api.interceptors.request.use(config => {
    const token = localStorage.getItem(ACCESS)
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  api.interceptors.response.use(
    r => r,
    async error => {
      const original = error.config
      const refresh = localStorage.getItem(REFRESH)
      if (error.response?.status === 401 && refresh && !original._retry) {
        original._retry = true
        try {
          const { data } = await api.post('/auth/refresh/', { refresh })
          localStorage.setItem(ACCESS, data.access)
          original.headers.Authorization = `Bearer ${data.access}`
          return api(original)
        } catch {
          onLogout?.()
        }
      }
      return Promise.reject(error)
    }
  )
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const logout = () => {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
    setUser(null)
  }

  useEffect(() => {
    setupAuthInterceptors(logout)
    const token = localStorage.getItem(ACCESS)
    if (token) {
      api.get('/auth/me/').then(r => setUser(r.data)).catch(() => logout()).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email, password) => {
    const { data } = await api.post('/auth/login/', { email, password })
    localStorage.setItem(ACCESS, data.access)
    localStorage.setItem(REFRESH, data.refresh)
    const me = await api.get('/auth/me/')
    setUser(me.data)
    return me.data
  }

  const refreshMe = async () => {
    const me = await api.get('/auth/me/')
    setUser(me.data)
    return me.data
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
