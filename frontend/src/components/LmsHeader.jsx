import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth'
import { PANEL_URL } from '../api'
import logo from '../assets/landing/logo-ingenioblocks.svg'

export default function LmsHeader() {
  const { user, logout } = useAuth()

  /* Salida a la portada con navegación del navegador, no del router.

     Con navigate('/') quedaba en /login: al vaciarse el usuario, RequireAuth
     alcanzaba a pintar <Navigate to="/login"> desde la ruta protegida y esa
     redirección pisaba el destino. No se arregla cambiando el orden ni con
     flushSync, porque React Router emite el cambio de ruta como transición de
     baja prioridad y React lo posterga igual.

     Un cambio de página real no compite con el router. Además deja el sitio
     limpio: no sobrevive nada del usuario anterior en memoria. El aviso al
     servidor viaja con keepalive (ver logout en auth.jsx), así que la recarga
     no lo corta. */
  const handleLogout = () => {
    // replace() y no assign(): reemplaza la entrada actual del historial en vez
    // de agregar una, así el botón "atrás" no devuelve a la página que se acaba
    // de abandonar al cerrar sesión.
    // Va antes de logout() para que el navegador empiece a descargar la página
    // cuanto antes; logout() igual se ejecuta (replace no corta el script) y su
    // aviso al servidor sale con keepalive.
    window.location.replace('/')
    logout()
  }

  return (
    <header className="lms-header">
      <div className="lms-header-inner">
        <Link to="/" className="lms-logo">
          <img src={logo} alt="IngenioBlocks" />
        </Link>

        <nav className="lms-header-nav">
          <NavLink to="/mis-cursos" className="lms-navlink">Mis cursos</NavLink>
          <Link to="/#kits" className="lms-navlink">Tienda</Link>
          {user?.is_staff && (
            /* Solo cuentas de gestión. Desde que el login dejó de saltar al
               panel, esta es la vía para volver a él sin escribir la URL. */
            <a href={PANEL_URL} className="lms-navlink lms-navlink-panel">
              Panel de gestión
            </a>
          )}
          {user && (
            <>
              {/* El chip lleva al perfil: es donde la gente busca sus datos. */}
              <Link to="/mi-cuenta" className="lms-user-chip" title="Mi cuenta">
                {/* La inicial cuando no hay foto, y no una silueta genérica: en
                    un computador familiar es lo que distingue una cuenta de
                    otra de un vistazo. */}
                {user.avatar_url
                  ? <img src={user.avatar_url} alt="" className="avatar avatar-foto" />
                  : <span className="avatar">{user.email[0].toUpperCase()}</span>}
                <span className="mail">{user.email}</span>
              </Link>
              <button className="lms-logout" onClick={handleLogout}>Salir</button>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}

export function LmsLoader({ text = 'Cargando…' }) {
  return (
    <div className="lms-loader">
      <div className="blocks"><span /><span /><span /></div>
      {text}
    </div>
  )
}
