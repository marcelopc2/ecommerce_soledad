import { Navigate, Link } from 'react-router-dom'
import { useAuth } from '../auth'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './lms.css'

/* Puerta del modo soporte (ver auth.jsx y lms/soporte.py). El token ya se
   guardó al cargar la página; acá solo se espera a saber quién es el alumno y
   se pasa a su Aula. Si no hay modo soporte (el link ya se usó, venció o se
   abrió a mano), se explica cómo volver a entrar. */
export default function Soporte() {
  const { user, loading } = useAuth()

  if (loading) return <div className="loading">Cargando…</div>
  if (user?.soporte) return <Navigate to="/mis-cursos" replace />

  return (
    <div className="lms">
      <div className="lms-auth">
        <div className="shape s1" /><div className="shape s2" />
        <div className="shape s3" /><div className="shape s4" />

        <div className="lms-auth-card">
          <Link to="/"><img src={logo} alt="IngenioBlocks" className="logo" /></Link>
          <h1>Modo soporte terminado</h1>
          <p className="sub">
            El acceso de soporte venció, se cerró o el enlace ya no es válido.
            Para volver a entrar, ábrelo de nuevo desde el panel de gestión,
            en la ficha del alumno.
          </p>
          <Link to="/" className="lms-btn yellow">Ir al inicio</Link>
        </div>
      </div>
    </div>
  )
}
