import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import './lms.css'
import Cargando from '../components/Cargando'

const fmtDate = (d) => d
  ? new Date(d + 'T00:00:00').toLocaleDateString('es-CL', { day: 'numeric', month: 'long', year: 'numeric' })
  : ''

//: Los colores de la marca. Los bloques caen en estos y no en un arcoíris
//: cualquiera, para que la celebración se vea parte del sitio.
const COLORES = ['#ffcb00', '#8200db', '#00b8a9', '#ff6b6b', '#00a63e', '#590599']

//: Las piezas se calculan UNA vez al cargar el módulo y no en cada repintado.
//: Con `Math.random()` adentro del render, cada repintado movía todo el confeti
//: de lugar; además React pide que pintar sea predecible. La variedad sale de
//: multiplicar el índice por números primos: se ve desordenado y es siempre igual.
const PIEZAS = Array.from({ length: 34 }, (_, i) => ({
  izq: (i * 37) % 100,
  demora: ((i * 13) % 9) / 10,
  duracion: 2.4 + ((i * 7) % 16) / 10,
  giro: ((i * 97) % 720) - 360,
  tam: 8 + ((i * 5) % 9),
  color: COLORES[i % COLORES.length],
}))

/* Bloquecitos cayendo. Cuadrados y no estrellitas ni emojis: lo que el niño
 * acaba de armar son bloques, y la celebración habla el mismo idioma. Va por
 * encima de todo pero sin capturar el mouse, así puede seguir navegando. */
function Confeti() {
  return (
    <div className="lms-confeti" aria-hidden="true">
      {PIEZAS.map((p, i) => (
        <span key={i} style={{
          left: `${p.izq}%`,
          width: `${p.tam}px`,
          height: `${p.tam}px`,
          background: p.color,
          animationDelay: `${p.demora}s`,
          animationDuration: `${p.duracion}s`,
          '--giro': `${p.giro}deg`,
        }} />
      ))}
    </div>
  )
}

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
  // Se enciende SOLO en el momento de terminar el modelo, no al volver a
  // entrar: una fiesta que se repite cada visita deja de ser un premio.
  const [celebrar, setCelebrar] = useState(false)

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
      const reciencompletado = res.data.course_completed && !course.completed
      setCourse(c => ({
        ...c,
        pct: res.data.pct, done: res.data.done, total: res.data.total,
        completed: res.data.course_completed,
        lessons: c.lessons.map(l => l.id === lesson.id ? { ...l, completed: true } : l),
      }))
      if (reciencompletado) setCelebrar(true)
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

  // Recorrido paso a paso. La lista del costado sirve para saltar a cualquiera,
  // pero el camino normal es lineal, y sin estos botones hay que volver a la
  // barra lateral a buscar cuál seguía. En el teléfono esa barra queda arriba
  // del todo, así que el alumno tenía que subir, elegir y bajar en cada paso.
  const idx = course.lessons.findIndex(l => l.id === activeId)
  const anterior = idx > 0 ? course.lessons[idx - 1] : null
  const siguiente = idx >= 0 && idx < course.lessons.length - 1
    ? course.lessons[idx + 1]
    : null

  const irAlPaso = (leccion) => {
    if (!leccion) return
    setActiveId(leccion.id)
    setAviso('')
    // Solo en pantalla angosta: ahí la barra lateral va arriba y el contenido
    // nuevo queda fuera de la vista. En el escritorio el panel ya se ve, y
    // moverlo sería un salto sin motivo.
    if (window.innerWidth <= 900) {
      document.querySelector('.lms-lesson-panel')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

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
            <span className={'lms-course-progress-label' + (course.completed ? ' logrado' : '')}>
              {course.completed ? '✓ Modelo terminado' : `${course.pct}% · ${course.done} de ${course.total} pasos`}
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

        {/* El momento del logro. No se cierra solo a los pocos segundos a
            propósito: el niño acaba de terminar algo que le tomó semanas y
            merece quedarse mirándolo el rato que quiera. */}
        {celebrar && (
          <div className="lms-logro" role="status">
            <span className="lms-logro-marca" aria-hidden="true">✓</span>
            <div className="lms-logro-txt">
              <strong>¡Terminaste {course.title}!</strong>
              <span>Tu avance quedó guardado.</span>
            </div>
            <Link to="/mis-cursos" className="lms-btn yellow">Ver mis modelos</Link>
            <button type="button" className="lms-logro-cerrar"
                    onClick={() => setCelebrar(false)} aria-label="Cerrar">✕</button>
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
                        {busy ? <><Cargando />Guardando…</> : '✓ Marcar como visto'}
                      </button>
                )}

                {/* Un solo paso no necesita navegación: los dos botones
                    saldrían apagados y solo ocuparían lugar. */}
                {course.lessons.length > 1 && (
                  <nav className="lms-pasos-nav" aria-label="Pasos del curso">
                    <button type="button" className="lms-btn ghost"
                            onClick={() => irAlPaso(anterior)}
                            disabled={!anterior}>
                      ← Anterior
                    </button>
                    <span className="lms-pasos-pos">
                      Paso {idx + 1} de {course.lessons.length}
                    </span>
                    {/* En el último paso "Siguiente" queda apagado y no lleva
                        a ninguna parte: justo cuando el niño terminó el modelo,
                        el único botón encendido lo manda hacia atrás. Ahí se
                        cambia por la salida natural, que es volver a la lista a
                        buscar el modelo que sigue. */}
                    {siguiente ? (
                      <button type="button" className="lms-btn yellow"
                              onClick={() => irAlPaso(siguiente)}>
                        Siguiente →
                      </button>
                    ) : (
                      <Link to="/mis-cursos" className="lms-btn yellow">
                        Volver a mis modelos
                      </Link>
                    )}
                  </nav>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {celebrar && <Confeti />}
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
    // Un video propio va primero: si el recurso tiene archivo, ese es el bueno.
    // El embed de YouTube es el otro camino, para los videos largos.
    if (lesson.has_video_file) return <LessonVideo lesson={lesson} />
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

/* Video propio del Aula.
 *
 * Se baja como blob y no se apunta el <video> directo al endpoint porque la API
 * autentica por token en una cabecera, y un <video src="..."> no manda
 * cabeceras: apuntarlo directo daba 401. El blob queda en memoria del navegador,
 * así que se puede adelantar y retroceder sin problema.
 *
 * El costo es que el archivo se descarga entero antes de empezar: por eso estos
 * videos son para clips cortos y los largos van a YouTube (ver LessonVideoView). */
function LessonVideo({ lesson }) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let url
    let cancelled = false
    setSrc(null); setFailed(false)
    api.get(`/lms/lessons/${lesson.id}/video/`, { responseType: 'blob' })
      .then(res => {
        if (cancelled) return
        url = URL.createObjectURL(res.data)
        setSrc(url)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url) }
  }, [lesson.id])

  if (failed) return <div className="lms-locked"><span className="lock">🎬</span><strong>No se pudo cargar el video</strong></div>
  if (!src) return <div className="lms-image-loading">Cargando video…</div>
  return (
    <div className="lms-video-wrap" onContextMenu={e => e.preventDefault()}>
      {/* controlsList nodownload esconde el botón de descargar del reproductor
          del navegador; el clic derecho ya está tapado arriba. */}
      <video
        src={src}
        controls
        controlsList="nodownload noplaybackrate"
        disablePictureInPicture
        playsInline
        title={lesson.title}
      />
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
