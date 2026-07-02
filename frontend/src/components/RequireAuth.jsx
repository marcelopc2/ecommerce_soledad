import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

// Protege rutas. staffOnly=true además exige is_staff (para el panel de la clienta).
export default function RequireAuth({ children, staffOnly = false }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="loading">Cargando…</div>
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (staffOnly && !user.is_staff) return <Navigate to="/" replace />
  return children
}
