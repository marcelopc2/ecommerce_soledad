import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/') }

  return (
    <header className="App-header">
      <div className="header-inner">
        <Link to="/" className="header-link">
          <h1>🚀 IngenioBlocks</h1>
        </Link>
        <nav className="header-nav">
          {user ? (
            <>
              <Link to="/mis-cursos" className="nav-link">Mis cursos</Link>
              {user.is_staff && <Link to="/panel" className="nav-link nav-panel">Panel</Link>}
              <span className="nav-user">{user.email}</span>
              <button className="nav-logout" onClick={handleLogout}>Salir</button>
            </>
          ) : (
            <Link to="/login" className="nav-link">Iniciar sesión</Link>
          )}
        </nav>
      </div>
    </header>
  )
}
