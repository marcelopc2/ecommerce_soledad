import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { api, PANEL_URL } from '../api'
import { useAuth } from '../auth'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import heroNino from '../assets/landing/hero-nino.png'
import './landing.css'
import './login.css'

/* Adornos sueltos del diseño (cruces, triangulitos y puntos). */
const Cruz = ({ color, style }) => (
  <svg viewBox="0 0 16 16" style={style} className="lg-deco" aria-hidden="true">
    <path d="M2 2l12 12M14 2L2 14" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
  </svg>
)
const Triangulo = ({ color, style }) => (
  <svg viewBox="0 0 12 14" style={style} className="lg-deco" aria-hidden="true">
    <path d="M1 1l10 6-10 6z" fill={color} />
  </svg>
)
const Punto = ({ color, style }) => (
  <span className="lg-deco lg-punto" style={{ background: color, ...style }} aria-hidden="true" />
)

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
      if (me.is_staff && !location.state?.from) {
        // El panel de gestión ahora vive en el backend (Django).
        window.location.href = PANEL_URL
        return
      }
      // checkoutProduct: viene de un kit "solo para alumnos" de la portada;
      // se reenvía al checkout para retomar la compra donde quedó.
      const producto = location.state?.checkoutProduct
      navigate(location.state?.from || '/mis-cursos', {
        replace: true,
        state: producto ? { product: producto } : undefined,
      })
    } catch (err) {
      // 429 = bloqueo por intentos fallidos (django-axes). Hay que distinguirlo
      // de una clave mala: si no, la persona bloqueada sigue reintentando y
      // cada intento alarga el castigo.
      if (err.response?.status === 429) {
        setError(err.response.data?.error || 'Demasiados intentos. Intenta más tarde.')
      } else {
        setError('Email o contraseña incorrectos.')
      }
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
    <div className="lp lg">
      <section className="lg-hero">
        {/* Panel morado: ocupa la izquierda y el borde derecho queda por
            debajo de la tarjeta, que lo cruza igual que en el Figma. */}
        <div className="lg-panel" aria-hidden="true">
          <div className="lg-panel-grid" />
          <img src={heroNino} alt="" className="lg-panel-foto" />
        </div>

        <header className="lg-topbar">
          <Link to="/" aria-label="Ir al inicio">
            <img src={logo} alt="Ingenio Blocks" className="lg-logo" />
          </Link>
          <Link to="/" className="lg-btn-outline">volver a inicio</Link>
        </header>

        <div className="lg-inner">
          <div className="lg-copy">
            <h1>
              <span className="lg-amarillo">¡Bienvenido a tu Aula Virtual!</span>{' '}
              Explora, aprende y construye
            </h1>
            <p>
              Para ingresar a nuestra Aula Virtual, debes contar con una membresía
              activa. Recuerda que el acceso se incluye automáticamente al comprar tu
              Kit Estándar, el Pack de 8 Modelos o tu suscripción Ingenio Plus.
            </p>
            <p className="lg-copy-pregunta">¿Aún no tienes el tuyo?</p>
            <Link to="/#kits" className="lg-btn-light">comprar ahora</Link>
          </div>

          <div className="lg-card-wrap">
            <span className="lg-sq lg-sq-lila" aria-hidden="true" />
            <span className="lg-sq lg-sq-amarillo" aria-hidden="true" />

            <form className="lg-card" onSubmit={handleSubmit}>
              <h2 className="lg-card-hola">¡Hola!</h2>
              <p className="lg-card-sub">inicia sesión</p>

              {error && <p className="lg-msg lg-msg-error">{error}</p>}
              {resetSent && (
                <p className="lg-msg lg-msg-ok">
                  Si el email existe, te enviamos un enlace para restablecer tu contraseña.
                </p>
              )}

              <label className="lg-label" htmlFor="login-email">Correo Electrónico</label>
              <input
                id="login-email" type="email" className="lg-input" value={email}
                onChange={e => setEmail(e.target.value)} required autoFocus
              />

              <label className="lg-label" htmlFor="login-pass">Contraseña</label>
              <input
                id="login-pass" type="password" className="lg-input" value={password}
                onChange={e => setPassword(e.target.value)} required
              />

              <button type="button" className="lg-olvide" onClick={handleReset}>
                ¿Olvidaste tu contraseña?
              </button>

              <button type="submit" className="lg-btn-ingresar" disabled={busy}>
                {busy ? 'ingresando…' : 'ingresar'}
              </button>

              {/* La cuenta no se crea sola: nace al pagar un kit (ver
                  lms.services.grant_access_for_order), así que el enlace lleva
                  a los kits en vez de a un registro que no existe. */}
              <p className="lg-card-pie">
                ¿No tienes cuenta? <Link to="/#kits">Compra tu kit</Link>
              </p>
            </form>
          </div>
        </div>

        <Cruz color="#2f0053" style={{ width: 15, top: '7%', left: '38%' }} />
        <Cruz color="#ffcb00" style={{ width: 17, top: '58%', left: '62%' }} />
        <Cruz color="#ffcb00" style={{ width: 15, top: '57%', right: '11%' }} />
        <Triangulo color="#ffcb00" style={{ width: 13, top: '9%', right: '25%' }} />
        <Triangulo color="#2f0053" style={{ width: 13, top: '12%', right: '36%', transform: 'rotate(180deg)' }} />
        <Triangulo color="#ffcb00" style={{ width: 13, top: '43%', left: '39%' }} />
        <Punto color="rgba(255,255,255,.55)" style={{ top: '12%', left: '53%' }} />
        <Punto color="#2f0053" style={{ top: '11%', left: '9%', width: 9, height: 9 }} />
        <Punto color="#8200db" style={{ top: '34%', right: '13%' }} />
        <Punto color="#2f0053" style={{ top: '54%', right: '28%', width: 9, height: 9 }} />
      </section>

    </div>
  )
}
