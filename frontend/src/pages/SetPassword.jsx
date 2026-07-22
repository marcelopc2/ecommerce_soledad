import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './lms.css'

export default function SetPassword() {
  const { uid, token } = useParams()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres.'); return }
    if (password !== confirm) { setError('Las contraseñas no coinciden.'); return }
    setBusy(true)
    try {
      await api.post('/auth/set-password/', { uid, token, password })
      setDone(true)
      setTimeout(() => navigate('/login', { replace: true }), 2000)
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo definir la contraseña.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lms">
      <div className="lms-auth">
        <div className="shape s1" /><div className="shape s2" />
        <div className="shape s3" /><div className="shape s4" />

        <div className="lms-auth-card">
          <Link to="/"><img src={logo} alt="IngenioBlocks" className="logo" /></Link>
          <h1>Crea tu contraseña 🔑</h1>
          <p className="sub">Un paso más y entras a tus cursos.</p>

          {done ? (
            <p className="lms-form-ok">¡Listo! Redirigiéndote al inicio de sesión…</p>
          ) : (
            <>
              {error && <p className="lms-form-error">{error}</p>}
              <form onSubmit={handleSubmit}>
                <div className="lms-field">
                  <label htmlFor="sp-pass">Nueva contraseña</label>
                  <input id="sp-pass" type="password" placeholder="Mínimo 8 caracteres" value={password}
                    onChange={e => setPassword(e.target.value)} required autoFocus />
                </div>
                <div className="lms-field">
                  <label htmlFor="sp-confirm">Repite la contraseña</label>
                  <input id="sp-confirm" type="password" placeholder="••••••••" value={confirm}
                    onChange={e => setConfirm(e.target.value)} required />
                </div>
                <button className="lms-btn yellow" type="submit" disabled={busy}>
                  {busy ? 'Guardando…' : 'Guardar y continuar'}
                </button>
              </form>
            </>
          )}

          <div className="lms-auth-links">
            <Link to="/login" className="muted">Ir a iniciar sesión</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
