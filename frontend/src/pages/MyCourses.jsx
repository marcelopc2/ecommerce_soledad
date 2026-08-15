import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api, PANEL_URL } from '../api'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import { openDiploma } from '../lib/diploma'
import './lms.css'

export default function MyCourses() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const cargar = () => {
    setLoading(true)
    setError(false)
    api.get('/lms/my-courses/')
      .then(r => setData(r.data))
      // Un fallo de red NO es lo mismo que "no tienes cursos": antes los dos
      // se veían igual y un corte de conexión se leía como "perdí mi compra".
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }

  useEffect(cargar, [])

  if (loading) {
    return <div className="lms"><LmsHeader /><LmsLoader text="Cargando tus cursos…" /></div>
  }

  if (error) {
    return (
      <div className="lms">
        <LmsHeader />
        <div className="lms-content">
          <div className="lms-empty">
            <span className="big" aria-hidden="true">⚠️</span>
            <h3>No pudimos cargar tus cursos</h3>
            <p>
              Puede ser un problema de conexión. Tu compra y tu avance están a
              salvo: vuelve a intentarlo en un momento.
            </p>
            <button className="lms-btn yellow" onClick={cargar}>Reintentar</button>
          </div>
        </div>
      </div>
    )
  }

  const membership = data.membership
  // Cuenta de gestión mirando el Aula sin ser alumna: ve todo el contenido
  // desbloqueado. No hay membresía, así que se fuerza `active` para que las
  // tarjetas no se muestren como "membresía vencida".
  const preview = data.preview === true
  const active = preview ? true : membership?.active
  const expires = membership?.expires_at
    ? new Date(membership.expires_at).toLocaleDateString('es-CL')
    : null
  const items = data.items || []

  return (
    <div className="lms">
      <LmsHeader />

      <section className="lms-hero">
        <div className="deco d1" /><div className="deco d2" /><div className="deco d3" />
        <div className="lms-hero-inner">
          <div>
            <h1>{preview ? 'Vista previa del Aula' : 'Mi academia'}</h1>
            <p className="sub">
              {preview
                ? 'Así ve el Aula un alumno. Todo desbloqueado, sin guardar avance.'
                : 'Tu ruta de aprendizaje, paso a paso.'}
            </p>
          </div>
          <div className="lms-hero-right">
            {preview && (
              <span className="lms-mem-chip preview">👁 Cuenta de gestión</span>
            )}
            {membership && (
              active
                ? <span className="lms-mem-chip ok">✓ Membresía activa hasta el {expires}</span>
                : <>
                    <span className="lms-mem-chip bad">✕ Membresía vencida el {expires}</span>
                    <Link to="/#kits" className="lms-btn yellow">Renovar</Link>
                  </>
            )}
          </div>
        </div>
      </section>

      <div className="lms-content">
        {items.length === 0 ? (
          /* Dos situaciones muy distintas que antes mostraban el mismo texto:
             a alguien que acababa de pagar se le decía "compra un kit", que es
             lo peor que puede leer. Se distingue por si tiene membresía. */
          preview ? (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🧱</span>
              <h3>Todavía no hay cursos publicados</h3>
              <p>
                Cuando crees un curso en el panel aparecerá acá, tal como lo
                verá el alumno.
              </p>
              <a href={PANEL_URL} className="lms-btn yellow">Ir al panel</a>
            </div>
          ) : membership ? (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🎉</span>
              <h3>¡Tu acceso está activo!</h3>
              <p>
                Estamos preparando tu primer modelo. Te avisamos por correo
                apenas esté disponible: no tienes que hacer nada más.
              </p>
            </div>
          ) : (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🧱</span>
              <h3>Aún no tienes cursos</h3>
              <p>Al comprar un kit, su contenido aparece aquí automáticamente.</p>
              <Link to="/#kits" className="lms-btn yellow">Ver los kits</Link>
            </div>
          )
        ) : (
          <div className="lms-courses-grid">
            {items.map(it => it.type === 'diploma'
              ? <DiplomaCard key={`d${it.id}`} diploma={it} />
              : <CourseCard key={`c${it.id}`} course={it} active={active} onReady={cargar} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Re-renderiza cada minuto para que el contador «se abre en X» baje solo si el
// alumno deja la página abierta. El goteo es por día, así que con el minuto basta.
function useMinuteTick() {
  const [, set] = useState(0)
  useEffect(() => {
    const id = setInterval(() => set(t => t + 1), 60000)
    return () => clearInterval(id)
  }, [])
}

// Cuánto falta para que se abra, en lenguaje natural. El goteo compara fechas en
// hora de Chile y libera a las 00:00, así que el objetivo es la medianoche local
// de unlock_date (para un usuario en Chile, su medianoche = la del servidor).
function faltaTexto(unlockDate) {
  const objetivo = new Date(`${unlockDate}T00:00:00`).getTime()
  const diff = objetivo - Date.now()
  if (diff <= 0) return 'hoy'
  const dias = Math.floor(diff / 86400000)
  if (dias >= 2) return `en ${dias} días`
  if (dias === 1) return 'mañana'
  const horas = Math.floor(diff / 3600000)
  if (horas >= 1) return `en ${horas} h`
  return `en ${Math.max(1, Math.floor(diff / 60000))} min`
}

function CourseCard({ course: c, active, onReady }) {
  useMinuteTick()
  // Misterio: un curso que el goteo todavía no libera. Se oculta nombre, foto y
  // descripción para dar expectativa; queda solo el contador. La membresía
  // vencida NO es misterio (el alumno ya tuvo el curso), se muestra normal.
  const misterio = active && !c.completed && !c.unlocked
  const locked = !active || !c.unlocked
  const porFecha = c.lock_reason !== 'previo'

  // Cuando llega la hora exacta, recargar para que el curso se libere solo, sin
  // que el alumno tenga que refrescar. Un único timeout, no un sondeo.
  useEffect(() => {
    if (!misterio || !porFecha) return
    const objetivo = new Date(`${c.unlock_date}T00:00:00`).getTime()
    const falta = objetivo - Date.now()
    if (falta <= 0) { onReady?.(); return }
    const id = setTimeout(() => onReady?.(), falta + 1000)
    return () => clearTimeout(id)
  }, [misterio, porFecha, c.unlock_date, onReady])

  const cuerpo = (
    <>
      <div className="lms-course-cover">
        {misterio
          ? <span className="fallback misterio-ojos" aria-hidden="true">👀</span>
          : (c.image_url ? <img src={c.image_url} alt={c.title} /> : <span className="fallback">🧱</span>)}
        {c.completed ? (
          <span className="lock-badge done">✓ Completado</span>
        ) : !active ? (
          <span className="lock-badge">🔒 Membresía vencida</span>
        ) : !c.unlocked ? (
          /* Dos motivos de bloqueo, hay que distinguirlos: por fecha (goteo) va
             un contador; por curso previo, mostrar la fecha lucía un día YA
             PASADO y el apoderado creía que la plataforma fallaba. */
          c.lock_reason === 'previo' && c.required_course_title ? (
            <span className="lock-badge">🔒 Termina el modelo anterior</span>
          ) : (
            <span className="lock-badge">🔒 Se abre {faltaTexto(c.unlock_date)}</span>
          )
        ) : null}
      </div>
      <div className="lms-course-body">
        <h3>{misterio ? 'Un modelo nuevo 👀' : c.title}</h3>
        <p>{misterio
          ? (porFecha
              ? 'Se viene algo nuevo. Te avisamos por correo apenas se abra.'
              : 'Termina el modelo anterior para descubrir cuál es.')
          : c.description}</p>
        {active && c.unlocked && c.total > 0 && (
          <div className="lms-progress">
            <div className="lms-progress-track"><div className="lms-progress-bar" style={{ width: `${c.pct}%` }} /></div>
            <span className="lms-progress-label">{c.pct}%</span>
          </div>
        )}
        <div className="lms-course-foot">
          {misterio
            ? <span className="lms-lessons-chip muted">Muy pronto</span>
            : <>
                <span className="lms-lessons-chip">{c.done}/{c.total} pasos</span>
                <span className="go">
                  {!active ? 'Renovar para entrar' : c.completed ? 'Revisar →' : 'Entrar →'}
                </span>
              </>}
        </div>
      </div>
    </>
  )

  // Ni el curso misterio ni los de una membresía vencida son clickeables. El
  // misterio, para no dejar un callejón sin salida ni filtrar el nombre por la
  // URL (/curso/su-slug). El vencido, porque la carátula está justamente para
  // que se vea lo que ya no puede abrir: llevarlo a una pantalla de error se
  // siente como una falla de la plataforma, no como una invitación a renovar.
  if (misterio) return <div className="lms-course-card locked misterio">{cuerpo}</div>
  if (!active) return <div className="lms-course-card locked vencida">{cuerpo}</div>
  return <Link to={`/curso/${c.slug}`} className={'lms-course-card' + (locked ? ' locked' : '')}>{cuerpo}</Link>
}

function DiplomaCard({ diploma: d }) {
  const [busy, setBusy] = useState(false)
  const download = async () => {
    setBusy(true)
    try { await openDiploma(d.id) } finally { setBusy(false) }
  }
  return (
    <div className={'lms-diploma-card' + (d.unlocked ? ' unlocked' : ' locked')}>
      <div className="lms-diploma-medal">{d.unlocked ? '🏅' : '🔒'}</div>
      <h3>{d.title}</h3>
      <p>{d.unlocked
        ? '¡Felicitaciones! Completaste esta etapa y ganaste tu diploma.'
        : 'Completa los cursos anteriores para desbloquear este diploma.'}</p>
      {d.unlocked
        ? <button className="lms-btn yellow" onClick={download} disabled={busy}>
            {busy ? 'Preparando…' : '🎓 Descargar diploma'}
          </button>
        : <span className="lms-diploma-locked-tag">Bloqueado</span>}
    </div>
  )
}
