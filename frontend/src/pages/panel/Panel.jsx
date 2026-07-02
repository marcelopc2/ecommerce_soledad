import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useAuth } from '../../auth'
import PanelProducts from './PanelProducts'
import PanelCourses from './PanelCourses'
import PanelMemberships from './PanelMemberships'
import './panel.css'

export default function Panel() {
  const { user, logout } = useAuth()

  return (
    <div className="panel">
      <aside className="panel-sidebar">
        <div className="panel-brand">🚀 IngenioBlocks<span>Panel</span></div>
        <nav>
          <NavLink to="/panel/productos" className="panel-nav">📦 Productos</NavLink>
          <NavLink to="/panel/cursos" className="panel-nav">🎓 Cursos (LMS)</NavLink>
          <NavLink to="/panel/membresias" className="panel-nav">👤 Membresías</NavLink>
        </nav>
        <div className="panel-footer">
          <span>{user.email}</span>
          <button onClick={logout}>Salir</button>
        </div>
      </aside>

      <main className="panel-main">
        <Routes>
          <Route index element={<Navigate to="productos" replace />} />
          <Route path="productos" element={<PanelProducts />} />
          <Route path="cursos" element={<PanelCourses />} />
          <Route path="membresias" element={<PanelMemberships />} />
        </Routes>
      </main>
    </div>
  )
}
