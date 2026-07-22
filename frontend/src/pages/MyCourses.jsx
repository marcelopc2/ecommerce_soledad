import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import { openDiploma } from '../lib/diploma'
import './lms.css'

const fmtDate = (d) => d
  ? new Date(d + 'T00:00:00').toLocaleDateString('es-CL', { day: 'numeric', month: 'short' })
  : ''

export default function MyCourses() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/lms/my-courses/')
      .then(r => setData(r.data))
      .catch(() => setData({ membership: null, items: [] }))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="lms"><LmsHeader /><LmsLoader text="Cargando tus cursos…" /></div>
  }

  const membership = data.membership
  const active = membership?.active
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
            <h1>Mi academia</h1>
            <p className="sub">Tu ruta de aprendizaje, paso a paso.</p>
          </div>
          <div className="lms-hero-right">
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
          <div className="lms-empty">
            <span className="big">🧱</span>
            <h3>Aún no tienes cursos</h3>
            <p>Compra un kit en la tienda y su contenido aparecerá aquí automáticamente.</p>
            <Link to="/#kits" className="lms-btn yellow">Ir a la tienda</Link>
          </div>
        ) : (
          <div className="lms-courses-grid">
            {items.map(it => it.type === 'diploma'
              ? <DiplomaCard key={`d${it.id}`} diploma={it} />
              : <CourseCard key={`c${it.id}`} course={it} active={active} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function CourseCard({ course: c, active }) {
  const locked = !active || !c.unlocked
  return (
    <Link to={`/curso/${c.slug}`} className={'lms-course-card' + (locked ? ' locked' : '')}>
      <div className="lms-course-cover">
        {c.image_url ? <img src={c.image_url} alt={c.title} /> : <span className="fallback">🧱</span>}
        {c.completed ? (
          <span className="lock-badge done">✓ Completado</span>
        ) : !active ? (
          <span className="lock-badge">🔒 Bloqueado</span>
        ) : !c.unlocked ? (
          <span className="lock-badge">🔒 Disponible el {fmtDate(c.unlock_date)}</span>
        ) : null}
      </div>
      <div className="lms-course-body">
        <h3>{c.title}</h3>
        <p>{c.description}</p>
        {active && c.unlocked && c.total > 0 && (
          <div className="lms-progress">
            <div className="lms-progress-track"><div className="lms-progress-bar" style={{ width: `${c.pct}%` }} /></div>
            <span className="lms-progress-label">{c.pct}%</span>
          </div>
        )}
        <div className="lms-course-foot">
          <span className="lms-lessons-chip">{c.done}/{c.total} recursos</span>
          <span className="go">{c.completed ? 'Revisar →' : 'Entrar →'}</span>
        </div>
      </div>
    </Link>
  )
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
