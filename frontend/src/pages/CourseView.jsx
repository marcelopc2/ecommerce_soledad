import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, API_BASE } from '../api'
import Header from '../components/Header'

export default function CourseView() {
  const { slug } = useParams()
  const [course, setCourse] = useState(null)
  const [active, setLesson] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get(`/lms/courses/${slug}/`)
      .then(r => {
        setCourse(r.data)
        setLesson(r.data.lessons?.[0] || null)
      })
      .catch(err => setError(err.response?.status === 403 ? 'No tienes acceso a este curso.' : 'Error al cargar el curso.'))
      .finally(() => setLoading(false))
  }, [slug])

  const downloadPdf = async (lessonId, title) => {
    try {
      const res = await api.get(`/lms/lessons/${lessonId}/pdf/`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url; a.download = `${title}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Necesitas una membresía activa para descargar este documento.')
    }
  }

  if (loading) return <div className="App"><Header /><div className="loading">Cargando curso…</div></div>
  if (error) return (
    <div className="App"><Header />
      <div className="checkout"><p className="form-error">{error}</p><Link to="/mis-cursos" className="back-link">← Mis cursos</Link></div>
    </div>
  )

  const membershipActive = course.membership_active

  return (
    <div className="App">
      <Header />
      <div className="course-view">
        <Link to="/mis-cursos" className="back-link">← Mis cursos</Link>
        <h2 className="checkout-title">{course.title}</h2>

        {!membershipActive && (
          <div className="membership-banner expired">
            ⚠️ Tu membresía está vencida. Renueva para ver los videos y descargar los documentos.
            <Link to="/" className="renew-link">Renovar</Link>
          </div>
        )}

        <div className="course-layout">
          <div className="lesson-list">
            {course.lessons.map(l => (
              <button key={l.id}
                className={'lesson-item' + (active?.id === l.id ? ' selected' : '')}
                onClick={() => setLesson(l)}>
                <span className="lesson-icon">{l.lesson_type === 'VIDEO' ? '▶️' : '📄'}</span>
                {l.order}. {l.title}
              </button>
            ))}
          </div>

          <div className="lesson-content">
            {!active ? <p>Este curso aún no tiene lecciones.</p> : (
              active.lesson_type === 'VIDEO' ? (
                membershipActive && active.video_embed_url ? (
                  <div className="video-wrap">
                    <iframe src={active.video_embed_url} title={active.title}
                      frameBorder="0" allowFullScreen></iframe>
                  </div>
                ) : (
                  <div className="locked-content">🔒 El video está disponible con una membresía activa.</div>
                )
              ) : (
                <div className="pdf-block">
                  <p>📄 Documento: <strong>{active.title}</strong></p>
                  {membershipActive ? (
                    <button className="btn-primary" onClick={() => downloadPdf(active.id, active.title)}>
                      Descargar PDF
                    </button>
                  ) : (
                    <div className="locked-content">🔒 Disponible con una membresía activa.</div>
                  )}
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
