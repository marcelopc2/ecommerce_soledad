import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import Header from '../components/Header'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [resetSent, setResetSent] = useState(false)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const me = await login(email, password)
      const dest = location.state?.from || (me.is_staff ? '/panel' : '/mis-cursos')
      navigate(dest, { replace: true })
    } catch {
      setError('Email o contraseña incorrectos.')
    } finally {
      setBusy(false)
    }
  }

  const handleReset = async () => {
    if (!email) { setError('Escribe tu email para enviarte el enlace.'); return }
    await api.post('/auth/request-reset/', { email })
    setResetSent(true); setError('')
  }

  return (
    <div className="App">
      <Header />
      <div className="auth-card">
        <h2>Iniciar sesión</h2>
        <form onSubmit={handleSubmit}>
          <input className="field" type="email" placeholder="Email" value={email}
            onChange={e => setEmail(e.target.value)} required />
          <input className="field" type="password" placeholder="Contraseña" value={password}
            onChange={e => setPassword(e.target.value)} required />
          {error && <p className="form-error">{error}</p>}
          {resetSent && <p className="form-ok">Si el email existe, te enviamos un enlace para restablecer tu contraseña.</p>}
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
        <button className="link-plain" onClick={handleReset}>¿Olvidaste tu contraseña?</button>
        <p className="auth-foot"><Link to="/">← Volver a la tienda</Link></p>
      </div>
    </div>
  )
}
