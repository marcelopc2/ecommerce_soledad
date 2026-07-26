import axios from 'axios'

// Base de la API de Django.
// En desarrollo apunta al backend local; en producción se compila con
// VITE_API_BASE=/api (mismo dominio, servido por nginx).
// localhost y no 127.0.0.1 a propósito: el navegador los trata como sitios
// distintos, y con 127.0.0.1 la cookie de sesión (SameSite=Lax) no viajaría
// desde localhost:5173 y el panel volvería a pedir la clave en desarrollo.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

// Panel de gestión de la clienta (Django templates, servido por el backend).
export const PANEL_URL = API_BASE.replace(/\/api\/?$/, '') + '/gestion/'

// withCredentials: deja pasar la cookie de sesión de Django, la que mantiene
// abierto el panel de gestión. La autenticación de la API sigue siendo el token.
export const api = axios.create({ baseURL: API_BASE, withCredentials: true })
