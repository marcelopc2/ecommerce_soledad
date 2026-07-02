import { useState, useEffect } from 'react'
import { api } from '../../api'

export default function PanelMemberships() {
  const [items, setItems] = useState([])

  useEffect(() => { api.get('/cms/memberships/').then(r => setItems(r.data)) }, [])

  return (
    <div>
      <div className="panel-head"><h2>Membresías</h2></div>
      <table className="panel-table">
        <thead><tr><th>Alumno</th><th>Cursos</th><th>Estado</th><th>Vence</th></tr></thead>
        <tbody>
          {items.map(m => (
            <tr key={m.id}>
              <td>{m.email}</td>
              <td>{m.courses_count}</td>
              <td>{m.is_active ? '✅ Activa' : '⚠️ Vencida'}</td>
              <td>{new Date(m.expires_at).toLocaleDateString('es-CL')}</td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan="4" className="hint">Aún no hay membresías.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
