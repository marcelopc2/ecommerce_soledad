import axios from 'axios'

// Base de la API de Django.
// En desarrollo apunta al backend local; en producción se compila con
// VITE_API_BASE=/api (mismo dominio, servido por nginx).
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api'

// Panel de gestión de la clienta (Django templates, servido por el backend).
export const PANEL_URL = API_BASE.replace(/\/api\/?$/, '') + '/gestion/'

export const api = axios.create({ baseURL: API_BASE })
