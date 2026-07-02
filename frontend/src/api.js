import axios from 'axios'

// Base de la API de Django.
export const API_BASE = 'http://127.0.0.1:8000/api'

export const api = axios.create({ baseURL: API_BASE })
