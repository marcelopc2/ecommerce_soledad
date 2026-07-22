import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import logo from '../assets/landing/logo-ingenioblocks.svg'

export default function LmsHeader() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/') }

  return (
    <header className="lms-header">
      <div className="lms-header-inner">
        <Link to="/" className="lms-logo">
          <img src={logo} alt="IngenioBlocks" />
        </Link>

        <nav className="lms-header-nav">
          <NavLink to="/mis-cursos" className="lms-navlink">Mis cursos</NavLink>
          <Link to="/#kits" className="lms-navlink">Tienda</Link>
          {user && (
            <>
              {/* El chip lleva al perfil: es donde la gente busca sus datos. */}
              <Link to="/mi-cuenta" className="lms-user-chip" title="Mi cuenta">
                <span className="avatar">{user.email[0].toUpperCase()}</span>
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
