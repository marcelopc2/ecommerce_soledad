import { useEffect } from 'react'
import { useAuth } from '../auth'
import './banda-soporte.css'

/* Franja fija mientras alguien del equipo mira el Aula como un alumno (modo
   soporte). Tiene que ser imposible de pasar por alto: quien la ve debe saber
   en todo momento que no está en su propia cuenta. Al vencer el tiempo se sale
   sola, sin esperar a que falle alguna petición. */
export default function BandaSoporte() {
  const { user, logout } = useAuth()
  const soporte = user?.soporte

  const vence = soporte?.vence

  const salir = () => {
    logout()
    window.location.replace('/soporte')
  }

  useEffect(() => {
    if (!vence) return
    const t = setTimeout(salir, Math.max(new Date(vence).getTime() - Date.now(), 0))
    return () => clearTimeout(t)
    // salir cambia en cada render (logout no es estable): con él en la lista,
    // el temporizador se reprogramaría siempre; basta con la hora de término.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vence])

  if (!soporte) return null
  const hora = new Date(vence).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })

  return (
    <div className="banda-soporte" role="status">
      <span>
        <strong>Modo soporte:</strong> estás viendo la cuenta de <strong>{user.email}</strong>.
        Solo para mirar · termina a las {hora}.
      </span>
      <button type="button" onClick={salir}>Salir</button>
    </div>
  )
}
