import { useState, useEffect } from 'react'
import { api } from '../../api'

const EMPTY = {
  name: '', slug: '', description: '', price: 0, stock: 0,
  is_digital: false, is_active: true, access_months: 12,
  category: '', courses: [],
}

export default function PanelProducts() {
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [courses, setCourses] = useState([])
  const [editing, setEditing] = useState(null) // objeto en edición o null
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    api.get('/cms/products/').then(r => setProducts(r.data))
    api.get('/cms/categories/').then(r => setCategories(r.data))
    api.get('/cms/courses/').then(r => setCourses(r.data))
  }
  useEffect(load, [])

  const startNew = () => { setEditing({ ...EMPTY }); setError('') }
  const startEdit = (p) => setEditing({
    ...p, category: p.category || '', courses: p.courses || [],
  })

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setError('')
    const payload = { ...editing, category: editing.category || null }
    try {
      if (editing.id) await api.put(`/cms/products/${editing.id}/`, payload)
      else await api.post('/cms/products/', payload)
      setEditing(null); load()
    } catch (err) {
      setError(JSON.stringify(err.response?.data || 'Error al guardar'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (p) => {
    if (!confirm(`¿Eliminar "${p.name}"?`)) return
    await api.delete(`/cms/products/${p.id}/`); load()
  }

  const toggleCourse = (id) => {
    const has = editing.courses.includes(id)
    setEditing({ ...editing, courses: has ? editing.courses.filter(c => c !== id) : [...editing.courses, id] })
  }

  return (
    <div>
      <div className="panel-head">
        <h2>Productos</h2>
        <button className="btn-primary" onClick={startNew}>+ Nuevo producto</button>
      </div>

      <table className="panel-table">
        <thead><tr><th>Nombre</th><th>Precio</th><th>Stock</th><th>Tipo</th><th>Activo</th><th></th></tr></thead>
        <tbody>
          {products.map(p => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td>${parseInt(p.price).toLocaleString('es-CL')}</td>
              <td>{p.stock}</td>
              <td>{p.is_digital ? 'Digital' : 'Físico'}</td>
              <td>{p.is_active ? '✅' : '—'}</td>
              <td className="row-actions">
                <button onClick={() => startEdit(p)}>Editar</button>
                <button className="danger" onClick={() => remove(p)}>Eliminar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <form className="modal" onClick={e => e.stopPropagation()} onSubmit={save}>
            <h3>{editing.id ? 'Editar' : 'Nuevo'} producto</h3>
            <label>Nombre<input className="field" value={editing.name}
              onChange={e => setEditing({ ...editing, name: e.target.value })} required /></label>
            <label>Slug (URL)<input className="field" value={editing.slug}
              onChange={e => setEditing({ ...editing, slug: e.target.value })} required /></label>
            <label>Descripción<textarea className="field" value={editing.description}
              onChange={e => setEditing({ ...editing, description: e.target.value })} /></label>
            <div className="row">
              <label>Precio (CLP)<input className="field" type="number" value={editing.price}
                onChange={e => setEditing({ ...editing, price: e.target.value })} /></label>
              <label>Stock<input className="field" type="number" value={editing.stock}
                onChange={e => setEditing({ ...editing, stock: e.target.value })} /></label>
              <label>Meses acceso LMS<input className="field" type="number" value={editing.access_months}
                onChange={e => setEditing({ ...editing, access_months: e.target.value })} /></label>
            </div>
            <label>Categoría
              <select className="field" value={editing.category}
                onChange={e => setEditing({ ...editing, category: e.target.value })}>
                <option value="">— Sin categoría —</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <div className="checks">
              <label className="check"><input type="checkbox" checked={editing.is_digital}
                onChange={e => setEditing({ ...editing, is_digital: e.target.checked })} /> Producto digital</label>
              <label className="check"><input type="checkbox" checked={editing.is_active}
                onChange={e => setEditing({ ...editing, is_active: e.target.checked })} /> Activo</label>
            </div>
            <fieldset className="courses-pick">
              <legend>Cursos que otorga esta compra</legend>
              {courses.length === 0 && <p className="hint">Aún no hay cursos. Créalos en la sección Cursos.</p>}
              {courses.map(c => (
                <label key={c.id} className="check">
                  <input type="checkbox" checked={editing.courses.includes(c.id)}
                    onChange={() => toggleCourse(c.id)} /> {c.title}
                </label>
              ))}
            </fieldset>
            {error && <p className="form-error">{error}</p>}
            <div className="modal-actions">
              <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
              <button className="btn-primary" type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
