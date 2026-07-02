import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header'

export default function MyCourses() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/lms/my-courses/')
      .then(r => setData(r.data))
      .catch(() => setData({ membership: null, courses: [] }))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="App"><Header /><div className="loading">Cargando tus cursos…</div></div>

  const membership = data.membership
  const active = membership?.active
  const expires = membership?.expires_at
    ? new Date(membership.expires_at).toLocaleDateString('es-CL')
    : null

  return (
    <div className="App">
      <Header />
      <div className="checkout">
        <h2 className="checkout-title">Mis cursos</h2>

        {membership && (
          <div className={'membership-banner ' + (active ? 'active' : 'expired')}>
            {active
              ? <>✅ Membresía activa hasta el <strong>{expires}</strong></>
              : <>⚠️ Tu membresía venció el <strong>{expires}</strong>. Renueva para volver a ver el contenido.
                  <Link to="/" className="renew-link">Renovar</Link></>}
          </div>
        )}

        {(!data.courses || data.courses.length === 0) ? (
          <p className="empty-state">Aún no tienes cursos. Compra un producto para acceder a su contenido.
            <br /><Link to="/">Ver productos →</Link></p>
        ) : (
          <div className="courses-grid">
            {data.courses.map(c => (
              <Link key={c.id} to={`/curso/${c.slug}`} className={'course-card' + (active ? '' : ' locked')}>
                {c.image_url && <img src={c.image_url} alt={c.title} className="course-img" />}
                <div className="course-body">
                  <h3>{c.title}</h3>
                  <p>{c.description}</p>
                  <span className="course-meta">{c.lessons_count} lección(es){active ? '' : ' · 🔒 bloqueado'}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
