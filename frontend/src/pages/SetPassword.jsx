import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header'

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
    <div className="App">
      <Header />
      <div className="auth-card">
        <h2>Define tu contraseña</h2>
        {done ? (
          <p className="form-ok">¡Listo! Redirigiéndote al inicio de sesión…</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <input className="field" type="password" placeholder="Nueva contraseña" value={password}
              onChange={e => setPassword(e.target.value)} required />
            <input className="field" type="password" placeholder="Repite la contraseña" value={confirm}
              onChange={e => setConfirm(e.target.value)} required />
            {error && <p className="form-error">{error}</p>}
            <button className="btn-primary" type="submit" disabled={busy}>
              {busy ? 'Guardando…' : 'Guardar contraseña'}
            </button>
          </form>
        )}
        <p className="auth-foot"><Link to="/login">Ir a iniciar sesión</Link></p>
      </div>
    </div>
  )
}
