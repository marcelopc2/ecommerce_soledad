import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import './lms.css'

const fmtDate = (d) => d
  ? new Date(d + 'T00:00:00').toLocaleDateString('es-CL', { day: 'numeric', month: 'long', year: 'numeric' })
  : ''

export default function CourseView() {
  const { slug } = useParams()
  const [course, setCourse] = useState(null)
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [unlockDate, setUnlockDate] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get(`/lms/courses/${slug}/`)
      .then(r => {
        setCourse(r.data)
        setActiveId(r.data.lessons?.[0]?.id ?? null)
      })
      .catch(err => {
        if (err.response?.status === 403 && err.response?.data?.unlock_date) {
          setUnlockDate(err.response.data.unlock_date); setError('drip-locked')
        } else if (err.response?.status === 403) {
          setError('No tienes acceso a este curso.')
        } else {
          setError('Error al cargar el curso.')
        }
      })
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

  const markSeen = async (lesson) => {
    setBusy(true)
    try {
      const res = await api.post(`/lms/lessons/${lesson.id}/complete/`)
      setCourse(c => ({
        ...c,
        pct: res.data.pct, done: res.data.done, total: res.data.total,
        completed: res.data.course_completed,
        lessons: c.lessons.map(l => l.id === lesson.id ? { ...l, completed: true } : l),
      }))
    } catch {
      alert('No se pudo marcar el recurso. Intenta de nuevo.')
    } finally { setBusy(false) }
  }

  if (loading) return <div className="lms"><LmsHeader /><LmsLoader text="Cargando curso…" /></div>

  if (error) {
    const isDrip = error === 'drip-locked'
    return (
      <div className="lms">
        <LmsHeader />
        <div className="lms-content">
          <div className="lms-empty">
            <span className="big">{isDrip ? '📅' : '🔒'}</span>
            <h3>{isDrip ? 'Todavía no puedes entrar a este curso' : error}</h3>
            {isDrip && <p>Se desbloquea el <strong>{fmtDate(unlockDate)}</strong>, cuando completes el curso anterior.</p>}
            <Link to="/mis-cursos" className="lms-btn ghost">← Volver a mis cursos</Link>
          </div>
        </div>
      </div>
    )
  }

  const membershipActive = course.membership_active
  const active = course.lessons.find(l => l.id === activeId) || null

  return (
    <div className="lms">
      <LmsHeader />

      <div className="lms-content">
        <Link to="/mis-cursos" className="lms-back">← Mis cursos</Link>
        <h1 className="lms-course-title">{course.title}</h1>
        <span className="lms-title-underline" />

        {course.total > 0 && (
          <div className="lms-course-progress">
            <div className="lms-progress-track big"><div className="lms-progress-bar" style={{ width: `${course.pct}%` }} /></div>
            <span className="lms-course-progress-label">
              {course.completed ? '✓ Curso completado' : `${course.pct}% · ${course.done} de ${course.total} recursos`}
            </span>
          </div>
        )}

        {!membershipActive && (
          <div className="lms-expired-banner">
            <span>⚠️ Tu membresía está vencida. Renuévala para ver los videos y el material.</span>
            <Link to="/tienda" className="lms-btn yellow">Renovar</Link>
          </div>
        )}

        <div className="lms-classroom">
          <aside className="lms-playlist">
            <div className="lms-playlist-head">Contenido · {course.lessons.length} recurso{course.lessons.length === 1 ? '' : 's'}</div>
            {course.lessons.map(l => (
              <button key={l.id}
                className={'lms-lesson-item' + (activeId === l.id ? ' selected' : '')}
                onClick={() => setActiveId(l.id)}>
                <span className={'lms-lesson-ico ' + l.lesson_type.toLowerCase()}>
                  {l.lesson_type === 'VIDEO' ? '▶' : l.lesson_type === 'PDF' ? '📄' : '🖼'}
                </span>
                <span className="lms-lesson-meta">
                  <span className="lms-lesson-num">Recurso {l.order}</span>
                  {l.title}
                </span>
                {l.completed && <span className="lms-lesson-check">✓</span>}
              </button>
            ))}
          </aside>

          <div className="lms-lesson-panel">
            {!active ? (
              <div className="lms-empty"><span className="big">🎬</span><h3>Este curso aún no tiene recursos</h3></div>
            ) : (
              <>
                <h2>{active.order}. {active.title}</h2>
                <LessonBody lesson={active} membershipActive={membershipActive} onDownloadPdf={downloadPdf} />
                {active.description && <p className="lms-lesson-desc">{active.description}</p>}

                {membershipActive && (
                  active.completed
                    ? <div className="lms-lesson-done">✓ Ya viste este recurso</div>
                    : <button className="lms-btn yellow lms-mark-btn" onClick={() => markSeen(active)} disabled={busy}>
                        {busy ? 'Guardando…' : '✓ Marcar como visto'}
                      </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function LessonBody({ lesson, membershipActive, onDownloadPdf }) {
  if (!membershipActive) {
    return (
      <div className="lms-locked">
        <span className="lock">🔒</span>
        <strong>Este contenido está disponible con membresía activa</strong>
        <Link to="/tienda" className="lms-btn yellow">Renovar membresía</Link>
      </div>
    )
  }
  if (lesson.lesson_type === 'VIDEO') {
    return lesson.video_embed_url
      ? <div className="lms-video-wrap"><iframe src={lesson.video_embed_url} title={lesson.title} allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /></div>
      : <div className="lms-locked"><span className="lock">🎬</span><strong>Video no disponible</strong></div>
  }
  if (lesson.lesson_type === 'IMAGE') {
    return <LessonImage lesson={lesson} />
  }
  // PDF
  return (
    <div className="lms-pdf-card">
      <span className="pdf-ico">📄</span>
      <div className="info"><strong>{lesson.title}</strong><span>Documento PDF descargable</span></div>
      <button className="lms-btn yellow" onClick={() => onDownloadPdf(lesson.id, lesson.title)}>Descargar</button>
    </div>
  )
}

function LessonImage({ lesson }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let url
    let cancelled = false
    setSrc(null); setFailed(false)
    api.get(`/lms/lessons/${lesson.id}/image/`, { responseType: 'blob' })
      .then(res => {
        if (cancelled) return
        url = URL.createObjectURL(res.data)
        setSrc(url)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url) }
  }, [lesson.id])

  if (failed) return <div className="lms-locked"><span className="lock">🖼</span><strong>No se pudo cargar la imagen</strong></div>
  if (!src) return <div className="lms-image-loading">Cargando imagen…</div>
  return <div className="lms-image-wrap"><img src={src} alt={lesson.title} /></div>
}
