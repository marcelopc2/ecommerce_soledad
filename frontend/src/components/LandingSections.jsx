/**
 * Secciones de la portada que se reutilizan en otras pantallas (login, etc.).
 * Viven acá y no en Landing.jsx para tener una sola fuente: si cambia el correo
 * de contacto o un link del footer, cambia en todas las páginas a la vez.
 *
 * Los estilos son los de landing.css; quien las use tiene que envolverlas en un
 * contenedor con la clase `lp` (varias reglas están scopeadas como `.lp .lp-h2`).
 */
import { useState } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { api } from '../api'
import logo from '../assets/landing/logo-ingenioblocks.svg'

const IconMail = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffcb00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="4" width="20" height="16" rx="3" /><path d="m2 7 10 7L22 7" />
  </svg>
)

const IconPhone = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffcb00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
)

const IconPin = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffcb00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z" /><circle cx="12" cy="10" r="3" />
  </svg>
)

const IconInstagram = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" /><circle cx="12" cy="12" r="4" /><line x1="17.5" y1="6.5" x2="17.5" y2="6.5" strokeWidth="3" />
  </svg>
)

const IconFacebook = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff">
    <path d="M14 13.5h2.5l1-4H14v-2c0-1.03 0-2 2-2h1.5V2.14C17.17 2.1 15.97 2 14.7 2 12.06 2 10.2 3.66 10.2 6.7v2.8H7v4h3.2V22h3.8v-8.5z" />
  </svg>
)

const IconYoutube = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="#fff">
    <path d="M23 7.2s-.2-1.6-.9-2.3c-.9-.9-1.9-.9-2.4-1C16.6 3.6 12 3.6 12 3.6s-4.6 0-7.7.3c-.5.1-1.5.1-2.4 1-.7.7-.9 2.3-.9 2.3S.8 9.1.8 11v1.8c0 1.9.2 3.8.2 3.8s.2 1.6.9 2.3c.9.9 2 .9 2.5 1 1.8.2 7.6.3 7.6.3s4.6 0 7.7-.4c.5-.1 1.5-.1 2.4-1 .7-.7.9-2.3.9-2.3s.2-1.9.2-3.8V11c0-1.9-.2-3.8-.2-3.8zM9.8 14.9V8.5l6.2 3.2-6.2 3.2z" />
  </svg>
)

export function Contacto() {
  const [form, setForm] = useState({ nombre: '', apellido: '', email: '', telefono: '', comentarios: '' })
  const [estado, setEstado] = useState('idle') // idle | enviando | ok | error
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const enviar = (e) => {
    e.preventDefault()
    setEstado('enviando')
    api.post('/catalog/contacto/', form)
      .then(() => {
        setEstado('ok')
        setForm({ nombre: '', apellido: '', email: '', telefono: '', comentarios: '' })
      })
      .catch(() => setEstado('error'))
  }

  return (
    <section className="lp-contacto" id="contacto">
      <div className="lp-contacto-inner">
        <div className="lp-contacto-info">
          <span className="lp-chip lp-chip-outline">estamos para tí</span>
          <h2 className="lp-h2 lp-h2-white">contacto</h2>
          <span className="lp-underline" style={{ margin: '0 0 36px' }} />
          <ul>
            <li><IconMail /> E-mail: contacto@ingenioblocks.com</li>
            <li><IconPhone /> Teléfono: +56 9 8502 6926</li>
            <li><IconPin /> Ubicación: Las Condes, Santiago-Chile</li>
          </ul>
        </div>
        <form className="lp-contacto-form" onSubmit={enviar}>
          <p>
            Rellena el siguiente formulario y nuestros profesionales se contactarán
            directamente contigo.
          </p>
          <div className="lp-form-row">
            <input placeholder="Nombre" value={form.nombre} onChange={set('nombre')} required />
            <input placeholder="Apellido" value={form.apellido} onChange={set('apellido')} />
          </div>
          <div className="lp-form-row">
            <input type="email" placeholder="Email" value={form.email} onChange={set('email')} required />
            <input placeholder="Numero telefónico" value={form.telefono} onChange={set('telefono')} />
          </div>
          <input placeholder="Comentarios y sugerencias" value={form.comentarios} onChange={set('comentarios')} />
          <button type="submit" className="lp-btn-yellow lp-btn-cta" disabled={estado === 'enviando'}>
            {estado === 'enviando' ? 'enviando…' : 'contáctanos'}
          </button>
          {estado === 'ok' && (
            <p className="lp-contacto-msg lp-contacto-msg-ok">¡Gracias! Recibimos tu mensaje, te contactaremos pronto.</p>
          )}
          {estado === 'error' && (
            <p className="lp-contacto-msg lp-contacto-msg-error">
              No pudimos enviar tu mensaje. Intenta nuevamente o escríbenos a contacto@ingenioblocks.com.
            </p>
          )}
        </form>
      </div>
    </section>
  )
}

const NAV = [
  ['como-funciona', 'Cómo funciona'],
  ['beneficios', 'Beneficios'],
  ['kits', 'Kits'],
  ['quienes-somos', 'Quiénes somos'],
  ['contacto', 'Contacto'],
]

export function LandingFooter() {
  // Fuera de la portada esas secciones no existen en el DOM, así que el ancla
  // suelto no llevaría a ninguna parte: hay que volver a "/" primero.
  const enPortada = useLocation().pathname === '/'
  const href = (id) => (enPortada ? `#${id}` : `/#${id}`)

  return (
    <footer className="lp-footer">
      <img src={logo} alt="Ingenio Blocks" className="lp-footer-logo" />
      <div className="lp-footer-center">
        <nav>
          {NAV.map(([id, label]) => <a key={id} href={href(id)}>{label}</a>)}
        </nav>
        <nav className="lp-footer-legal">
          <Link to="/legal/terminos">Términos y condiciones</Link>
          <Link to="/legal/privacidad">Privacidad</Link>
          <Link to="/legal/retracto">Retracto y devoluciones</Link>
        </nav>
        <p>Todos los derechos reservados para Ingenio Blocks</p>
      </div>
      <div className="lp-social">
        <a href="https://instagram.com" target="_blank" rel="noreferrer" aria-label="Instagram"><IconInstagram /></a>
        <a href="https://facebook.com" target="_blank" rel="noreferrer" aria-label="Facebook"><IconFacebook /></a>
        <a href="https://youtube.com" target="_blank" rel="noreferrer" aria-label="YouTube"><IconYoutube /></a>
      </div>
    </footer>
  )
}
