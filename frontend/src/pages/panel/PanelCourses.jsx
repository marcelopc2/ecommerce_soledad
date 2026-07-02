import { useState, useEffect } from 'react'
import { api } from '../../api'

const EMPTY_COURSE = { title: '', slug: '', description: '', image_url: '', is_active: true }

export default function PanelCourses() {
  const [courses, setCourses] = useState([])
  const [editing, setEditing] = useState(null)      // curso en edición
  const [managing, setManaging] = useState(null)    // curso cuyas lecciones se gestionan
  const [error, setError] = useState('')

  const load = () => api.get('/cms/courses/').then(r => setCourses(r.data))
  useEffect(() => { load() }, [])

  const saveCourse = async (e) => {
    e.preventDefault(); setError('')
    try {
      if (editing.id) await api.put(`/cms/courses/${editing.id}/`, editing)
      else await api.post('/cms/courses/', editing)
      setEditing(null); load()
    } catch (err) { setError(JSON.stringify(err.response?.data || 'Error')) }
  }

  const removeCourse = async (c) => {
    if (!confirm(`¿Eliminar el curso "${c.title}" y sus lecciones?`)) return
    await api.delete(`/cms/courses/${c.id}/`); load()
  }

  return (
    <div>
      <div className="panel-head">
        <h2>Cursos (LMS)</h2>
        <button className="btn-primary" onClick={() => { setEditing({ ...EMPTY_COURSE }); setError('') }}>+ Nuevo curso</button>
      </div>

      <table className="panel-table">
        <thead><tr><th>Curso</th><th>Lecciones</th><th>Activo</th><th></th></tr></thead>
        <tbody>
          {courses.map(c => (
            <tr key={c.id}>
              <td>{c.title}</td>
              <td>{c.lessons?.length || 0}</td>
              <td>{c.is_active ? '✅' : '—'}</td>
              <td className="row-actions">
                <button onClick={() => setManaging(c)}>Lecciones</button>
                <button onClick={() => setEditing(c)}>Editar</button>
                <button className="danger" onClick={() => removeCourse(c)}>Eliminar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <form className="modal" onClick={e => e.stopPropagation()} onSubmit={saveCourse}>
            <h3>{editing.id ? 'Editar' : 'Nuevo'} curso</h3>
            <label>Título<input className="field" value={editing.title}
              onChange={e => setEditing({ ...editing, title: e.target.value })} required /></label>
            <label>Slug (URL)<input className="field" value={editing.slug}
              onChange={e => setEditing({ ...editing, slug: e.target.value })} required /></label>
            <label>Descripción<textarea className="field" value={editing.description}
              onChange={e => setEditing({ ...editing, description: e.target.value })} /></label>
            <label>Imagen de portada (URL)<input className="field" value={editing.image_url}
              onChange={e => setEditing({ ...editing, image_url: e.target.value })} /></label>
            <label className="check"><input type="checkbox" checked={editing.is_active}
              onChange={e => setEditing({ ...editing, is_active: e.target.checked })} /> Activo</label>
            {error && <p className="form-error">{error}</p>}
            <div className="modal-actions">
              <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
              <button className="btn-primary" type="submit">Guardar</button>
            </div>
          </form>
        </div>
      )}

      {managing && (
        <LessonsManager course={managing} onClose={() => { setManaging(null); load() }} />
      )}
    </div>
  )
}

function LessonsManager({ course, onClose }) {
  const [lessons, setLessons] = useState([])
  const [form, setForm] = useState({ title: '', order: 1, lesson_type: 'VIDEO', video_embed_url: '' })
  const [pdf, setPdf] = useState(null)
  const [error, setError] = useState('')

  const load = () => api.get(`/cms/lessons/?course=${course.id}`).then(r => setLessons(r.data))
  useEffect(() => { load() }, [])

  const add = async (e) => {
    e.preventDefault(); setError('')
    try {
      const fd = new FormData()
      fd.append('course', course.id)
      fd.append('title', form.title)
      fd.append('order', form.order)
      fd.append('lesson_type', form.lesson_type)
      if (form.lesson_type === 'VIDEO') fd.append('video_embed_url', form.video_embed_url)
      if (form.lesson_type === 'PDF' && pdf) fd.append('pdf_file', pdf)
      await api.post('/cms/lessons/', fd)
      setForm({ title: '', order: lessons.length + 1, lesson_type: 'VIDEO', video_embed_url: '' })
      setPdf(null); load()
    } catch (err) { setError(JSON.stringify(err.response?.data || 'Error')) }
  }

  const remove = async (l) => {
    if (!confirm(`¿Eliminar la lección "${l.title}"?`)) return
    await api.delete(`/cms/lessons/${l.id}/`); load()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal wide" onClick={e => e.stopPropagation()}>
        <h3>Lecciones · {course.title}</h3>
        <ul className="lessons-admin">
          {lessons.map(l => (
            <li key={l.id}>
              <span>{l.order}. {l.lesson_type === 'VIDEO' ? '▶️' : '📄'} {l.title}
                {l.pdf_filename ? ` (${l.pdf_filename})` : ''}</span>
              <button className="danger" onClick={() => remove(l)}>Eliminar</button>
            </li>
          ))}
          {lessons.length === 0 && <li className="hint">Sin lecciones aún.</li>}
        </ul>

        <form onSubmit={add} className="lesson-form">
          <h4>Agregar lección</h4>
          <div className="row">
            <input className="field" placeholder="Título" value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })} required />
            <input className="field field-sm" type="number" placeholder="Orden" value={form.order}
              onChange={e => setForm({ ...form, order: e.target.value })} />
            <select className="field" value={form.lesson_type}
              onChange={e => setForm({ ...form, lesson_type: e.target.value })}>
              <option value="VIDEO">Video</option>
              <option value="PDF">PDF</option>
            </select>
          </div>
          {form.lesson_type === 'VIDEO' ? (
            <input className="field" placeholder="URL de embed (YouTube/Vimeo)" value={form.video_embed_url}
              onChange={e => setForm({ ...form, video_embed_url: e.target.value })} />
          ) : (
            <input className="field" type="file" accept="application/pdf"
              onChange={e => setPdf(e.target.files[0])} />
          )}
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cerrar</button>
            <button className="btn-primary" type="submit">Agregar lección</button>
          </div>
        </form>
      </div>
    </div>
  )
}
