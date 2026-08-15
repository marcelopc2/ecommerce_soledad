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
  const [expiresAt, setExpiresAt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [aviso, setAviso] = useState('')   // errores puntuales, en la propia página

  useEffect(() => {
    api.get(`/lms/courses/${slug}/`)
      .then(r => {
        setCourse(r.data)
        setActiveId(r.data.lessons?.[0]?.id ?? null)
      })
      .catch(err => {
        // Tres motivos distintos para el mismo 403, y el apoderado necesita
        // distinguirlos: "todavía no te toca", "se te venció" y "esto no es
        // tuyo" se arreglan de maneras muy diferentes.
        if (err.response?.status === 403 && err.response?.data?.expired) {
          setExpiresAt(err.response.data.expires_at); setError('expired')
        } else if (err.response?.status === 403 && err.response?.data?.unlock_date) {
          setUnlockDate(err.response.data.unlock_date); setError('drip-locked')
        } else if (err.response?.status === 403) {
          setError('No tienes acceso a este curso.')
        } else {
          setError('Error al cargar el curso.')
        }
      })
      .finally(() => setLoading(false))
  }, [slug])

  const markSeen = async (lesson) => {
    setBusy(true)
    setAviso('')
    try {
      const res = await api.post(`/lms/lessons/${lesson.id}/complete/`)
      setCourse(c => ({
        ...c,
        pct: res.data.pct, done: res.data.done, total: res.data.total,
        completed: res.data.course_completed,
        lessons: c.lessons.map(l => l.id === lesson.id ? { ...l, completed: true } : l),
      }))
    } catch {
      setAviso('No pudimos guardar tu avance. Revisa tu conexión e intenta de nuevo.')
    } finally { setBusy(false) }
  }

  if (loading) return <div className="lms"><LmsHeader /><LmsLoader text="Cargando curso…" /></div>

  if (error) {
    const isDrip = error === 'drip-locked'
    const isExpired = error === 'expired'
    return (
      <div className="lms">
        <LmsHeader />
        <div className="lms-content">
          <div className="lms-empty">
            <span className="big">{isDrip ? '📅' : isExpired ? '⏳' : '🔒'}</span>
            <h3>
              {isDrip ? 'Todavía no puedes entrar a este curso'
                : isExpired ? 'Tu suscripción venció'
                : error}
            </h3>
            {isDrip && <p>Se desbloquea el <strong>{fmtDate(unlockDate)}</strong>, cuando completes el curso anterior.</p>}
            {isExpired && (
              <p>
                {expiresAt && <>Venció el <strong>{new Date(expiresAt).toLocaleDateString('es-CL')}</strong>. </>}
                Al renovar retomas justo donde quedaste: tu avance está guardado y
                no pierdes ningún modelo.
              </p>
            )}
            {isExpired && <Link to="/#kits" className="lms-btn yellow">Renovar mi acceso</Link>}
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
              {course.completed ? '✓ Curso completado' : `${course.pct}% · ${course.done} de ${course.total} pasos`}
            </span>
          </div>
        )}

        {/* `expired` y no `!membershipActive`: si llegó hasta acá con la
            suscripción caída es porque terminó este modelo y lo está repasando,
            así que el aviso no dice "no puedes ver esto" —lo está viendo— sino
            que para seguir con los que faltan hay que renovar. */}
        {course.expired && (
          <div className="lms-expired-banner">
            <span>⚠️ Tu suscripción venció. Puedes repasar los modelos que terminaste; renuévala para seguir con los que faltan.</span>
            <Link to="/#kits" className="lms-btn yellow">Renovar</Link>
          </div>
        )}

        {aviso && (
          <div className="lms-aviso" role="alert">
            <span>{aviso}</span>
            <button type="button" onClick={() => setAviso('')} aria-label="Cerrar aviso">✕</button>
          </div>
        )}

        <div className="lms-classroom">
          <aside className="lms-playlist">
            <div className="lms-playlist-head">Contenido · {course.lessons.length} paso{course.lessons.length === 1 ? '' : 's'}</div>
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
              <div className="lms-empty"><span className="big">🎬</span><h3>Este curso aún no tiene pasos</h3></div>
            ) : (
              <>
                <h2>{active.order}. {active.title}</h2>
                <LessonBody lesson={active} membershipActive={membershipActive} />
                {active.description && <p className="lms-lesson-desc">{active.description}</p>}

                {/* En vista previa no hay membresía donde guardar el avance,
                    así que el botón no se muestra: apretarlo solo daría error. */}
                {course.preview ? (
                  <div className="lms-lesson-done preview">
                    👁 Vista previa · el avance no se guarda
                  </div>
                ) : course.expired ? (
                  /* Repasando con la suscripción caída: el avance no se guarda,
                     así que el botón solo daría un error al apretarlo. */
                  active.completed
                    ? <div className="lms-lesson-done">✓ Ya lo hiciste</div>
                    : null
                ) : membershipActive && (
                  active.completed
                    ? <div className="lms-lesson-done">✓ ¡Listo, ya lo hiciste!</div>
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

function LessonBody({ lesson, membershipActive }) {
  if (!membershipActive) {
    return (
      <div className="lms-locked">
        <span className="lock">🔒</span>
        <strong>Este contenido está disponible con membresía activa</strong>
        <Link to="/#kits" className="lms-btn yellow">Renovar membresía</Link>
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
  return <LessonPdf lesson={lesson} />
}

// El manual se lee DENTRO del Aula: no hay botón de descargar. `#toolbar=0`
// esconde la barra del visor del navegador, que es donde vive el botón de
// guardar e imprimir. Chrome y Edge la respetan; Firefox no, así que ahí el
// botón sigue apareciendo. No hay forma de taparlo en todos los navegadores sin
// meter un visor propio de medio megabyte, y no vale la pena: quien quiera el
// archivo lo saca igual con una captura de pantalla.
function LessonPdf({ lesson }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let url
    let cancelled = false
    setSrc(null); setFailed(false)
    // Por blob y no por URL directa: así la dirección del archivo no queda a la
    // vista en el HTML para copiarla y pasarla por WhatsApp.
    api.get(`/lms/lessons/${lesson.id}/pdf/`, { responseType: 'blob' })
      .then(res => {
        if (cancelled) return
        url = URL.createObjectURL(res.data)
        setSrc(url + '#toolbar=0&navpanes=0&statusbar=0')
      })
      .catch(() => !cancelled && setFailed(true))
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url) }
  }, [lesson.id])

  if (failed) return <div className="lms-locked"><span className="lock">📄</span><strong>No se pudo cargar el documento</strong></div>
  if (!src) return <div className="lms-image-loading">Cargando documento…</div>
  return (
    <div className="lms-pdf-wrap">
      <iframe src={src} title={lesson.title} />
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
  return (
    <div className="lms-image-wrap" onContextMenu={e => e.preventDefault()}>
      <img src={src} alt={lesson.title} draggable="false" />
    </div>
  )
}
