import { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'
import { api, API_BASE } from './api'

const AuthContext = createContext(null)

const ACCESS = 'ib_access'
const REFRESH = 'ib_refresh'

/* Renueva la sesión. Tres cosas que antes estaban mal y juntas dejaban la
   página trabada en un bucle infinito de "401 en /auth/refresh/":

   1. El servidor ROTA el token de refresco (ROTATE_REFRESH_TOKENS): cada
      renovación entrega uno nuevo y deja el anterior en lista negra. Acá solo
      se guardaba el `access` y el refresh nuevo se tiraba. La primera
      renovación (a las 8 h) funcionaba; la segunda (a las 16 h) usaba el token
      viejo, ya en lista negra, y fallaba. Le pasaba a TODO el que dejara el
      Aula abierta un día.

   2. La renovación iba por la misma instancia `api`, así que su propio 401
      volvía a caer en el interceptor, que pedía otra renovación, que también
      fallaba... La marca `_retry` protegía al pedido original, no al de
      renovación, que es uno nuevo cada vez. Ahora va por `axios` pelado, fuera
      de los interceptores: su fallo no puede disparar nada.

   3. Si varias peticiones vencían juntas (Mis cursos pide varias), cada una
      lanzaba su propia renovación con el MISMO token. Con rotación, la primera
      lo invalida y las demás reciben 401: cierre de sesión al azar. Ahora hay
      una sola renovación en curso y las demás la esperan. */
let renovacionEnCurso = null

function renovarSesion() {
  if (!renovacionEnCurso) {
    const refresh = localStorage.getItem(REFRESH)
    renovacionEnCurso = axios
      .post(`${API_BASE}/auth/refresh/`, { refresh }, { withCredentials: true })
      .then(({ data }) => {
        localStorage.setItem(ACCESS, data.access)
        if (data.refresh) localStorage.setItem(REFRESH, data.refresh)
        return data.access
      })
      .finally(() => { renovacionEnCurso = null })
  }
  return renovacionEnCurso
}

// Inyecta el token en cada request y renueva la sesión una vez ante un 401.
// Devuelve la función que quita los interceptores: sin quitarlos, cada montaje
// del proveedor los apilaba y un solo 401 se atendía varias veces.
export function setupAuthInterceptors(onLogout) {
  const alPedir = api.interceptors.request.use(config => {
    const token = localStorage.getItem(ACCESS)
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  const alResponder = api.interceptors.response.use(
    r => r,
    async error => {
      const original = error.config
      if (error.response?.status !== 401 || !original || original._retry
          || !localStorage.getItem(REFRESH)) {
        return Promise.reject(error)
      }
      original._retry = true
      try {
        const access = await renovarSesion()
        original.headers.Authorization = `Bearer ${access}`
        return api(original)
      } catch {
        // Si fallaron varias peticiones juntas, todas llegan acá: solo la
        // primera cierra la sesión. Después ya no hay token y las demás pasan.
        if (localStorage.getItem(REFRESH)) onLogout?.()
        return Promise.reject(error)
      }
    }
  )

  return () => {
    api.interceptors.request.eject(alPedir)
    api.interceptors.response.eject(alResponder)
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  /* Cerrar sesión avisa al servidor, no solo borra el token de acá: hay que
     revocar el refresh token y, en las cuentas de gestión, cerrar además la
     sesión del panel (ver LogoutView). Sin esto, alguien podía "cerrar sesión"
     en el sitio y seguir entrando a /gestion/ en ese mismo computador.

     La limpieza local NO espera al servidor ni depende de que responda bien:
     si el aviso falla (sin internet, servidor caído), igual queda desconectado
     en este navegador, que es lo que la persona espera al hacer clic.

     Se usa fetch con keepalive y no axios porque quien llama a esto suele
     recargar la página enseguida (ver handleLogout en los headers): keepalive
     le garantiza al navegador que debe terminar de enviar la petición aunque la
     página se descargue. Con una petición normal se cancelaba a medio camino y
     el token quedaba sin revocar y la sesión del panel sin cerrar. */
  const logout = () => {
    const refresh = localStorage.getItem(REFRESH)
    const access = localStorage.getItem(ACCESS)
    fetch(`${API_BASE}/auth/logout/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: JSON.stringify({ refresh }),
      credentials: 'include',   // manda la cookie de sesión del panel
      keepalive: true,
    }).catch(() => {})
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
    setUser(null)
  }

  useEffect(() => {
    const quitarInterceptores = setupAuthInterceptors(logout)
    const token = localStorage.getItem(ACCESS)
    if (token) {
      api.get('/auth/me/').then(r => setUser(r.data)).catch(() => logout()).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
    return quitarInterceptores
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
