/**
 * Secciones de la portada que se reutilizan en otras pantallas (login, etc.).
 * Viven acá y no en Landing.jsx para tener una sola fuente: si cambia el correo
 * de contacto o un link del footer, cambia en todas las páginas a la vez.
 *
 * Los estilos son los de landing.css; quien las use tiene que envolverlas en un
 * contenedor con la clase `lp` (varias reglas están scopeadas como `.lp .lp-h2`).
 */
import { useState, useEffect, useLayoutEffect } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { api } from '../api'
// Variante oficial en blanco (entregada aparte del SVG reconstruido de Figma),
// pensada para fondos oscuros. Solo el footer, que fue el pedido explícito: el
// header (en Landing.jsx) sigue con el SVG de siempre y no hay razón para tocarlo.
import logoBlanco from '../assets/brand/logo-ingenioblocks-blanco.png'
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

export const IconInstagram = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" /><circle cx="12" cy="12" r="4" /><line x1="17.5" y1="6.5" x2="17.5" y2="6.5" strokeWidth="3" />
  </svg>
)

export const IconFacebook = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
    <path d="M14 13.5h2.5l1-4H14v-2c0-1.03 0-2 2-2h1.5V2.14C17.17 2.1 15.97 2 14.7 2 12.06 2 10.2 3.66 10.2 6.7v2.8H7v4h3.2V22h3.8v-8.5z" />
  </svg>
)

export const IconYoutube = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
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
          {/* lila (relleno) y no outline: en el Figma esta etiqueta es una
              pastilla clara con texto morado, igual que las del resto de la
              landing. Estaba como contorno transparente con texto blanco. */}
          <span className="lp-chip lp-chip-lila">estamos para ti</span>
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
          {/* textarea y no input: son comentarios abiertos y en una sola línea
              el texto se iba desplazando y no se podía releer lo escrito. */}
          <textarea
            placeholder="Comentarios y sugerencias"
            rows={3}
            maxLength={2000}
            value={form.comentarios}
            onChange={set('comentarios')}
          />
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
      <img src={logoBlanco} alt="Ingenio Blocks" className="lp-footer-logo" />
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


/* ---------- Encabezado ----------
   Vive acá y no en Landing.jsx porque ahora lo usan dos páginas: la portada y
   la vitrina de modelos. Tenerlo duplicado significaba que agregar una entrada
   al menú había que hacerlo en dos lados y uno se iba a olvidar.
*/

const SECCIONES_NAV = [
  ['como-funciona', 'Cómo funciona'],
  ['beneficios', 'Beneficios'],
  ['kits', 'Kits'],
  ['quienes-somos', 'Quiénes somos'],
  ['contacto', 'Contacto'],
]

const IconUser = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
  </svg>
)

const IconMenu = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round">
    <path d="M3 6h18M3 12h18M3 18h18" />
  </svg>
)

const IconClose = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export function LandingHeader({ active }) {
  const { user } = useAuth()
  const location = useLocation()
  const [menuAbierto, setMenuAbierto] = useState(false)
  const cls = (id) => (active === id ? 'active' : undefined)

  // Fuera de la portada los anclas no existen en la página: hay que volver a "/"
  // y recién ahí saltar. Landing.jsx se encarga del scroll al llegar con hash.
  const enPortada = location.pathname === '/'
  const enlaces = SECCIONES_NAV.map(([id, texto]) => ({
    id, texto, href: enPortada ? `#${id}` : `/#${id}`,
  }))

  useEffect(() => {
    if (!menuAbierto) return
    const alTeclear = (e) => { if (e.key === 'Escape') setMenuAbierto(false) }
    const overflowPrevio = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', alTeclear)
    return () => {
      document.body.style.overflow = overflowPrevio
      window.removeEventListener('keydown', alTeclear)
    }
  }, [menuAbierto])

  function itemsDeNav(alClick) {
    return enlaces.map(({ id, texto, href }) => (
      <a key={id} href={href} className={cls(id)} onClick={alClick}>{texto}</a>
    ))
  }

  return (
    <header className="lp-header">
      <Link to="/" className="lp-logo"><img src={logo} alt="Ingenio Blocks" /></Link>

      <nav className="lp-nav">
        {itemsDeNav()}
      </nav>

      <div className="lp-header-right">
        {user ? (
          <Link to="/mis-cursos" className="lp-login-btn">mis cursos <IconUser /></Link>
        ) : (
          <Link to="/login" className="lp-login-btn">iniciar sesión <IconUser /></Link>
        )}
        {/* Bajo 1200px la nav horizontal no cabe y se oculta; sin este botón la
            portada quedaba SIN navegación en celular, tablet y notebooks de 13". */}
        <button
          type="button"
          className="lp-menu-btn"
          aria-label={menuAbierto ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={menuAbierto}
          onClick={() => setMenuAbierto((v) => !v)}
        >
          {menuAbierto ? <IconClose /> : <IconMenu />}
        </button>
      </div>

      {menuAbierto && (
        <div className="lp-menu-movil" role="dialog" aria-modal="true" aria-label="Menú">
          <nav>
            {itemsDeNav(() => setMenuAbierto(false))}
          </nav>
          <Link
            to={user ? '/mis-cursos' : '/login'}
            className="lp-menu-movil-cta"
            onClick={() => setMenuAbierto(false)}
          >
            {user ? 'mis cursos' : 'iniciar sesión'} <IconUser />
          </Link>
        </div>
      )}
    </header>
  )
}


/* ---------- Decoraciones y revelado ----------
   Se movieron acá desde Landing.jsx cuando la vitrina de modelos pasó a
   necesitar lo mismo: son el lenguaje visual del sitio, no de una página.
*/

export const Sparkle = ({ size = 20, color = '#ffcb00', style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} style={style} className="lp-deco" aria-hidden="true">
    <path d="M12 0c.6 6.5 5.5 11.4 12 12-6.5.6-11.4 5.5-12 12-.6-6.5-5.5-11.4-12-12C6.5 11.4 11.4 6.5 12 0z" />
  </svg>
)

export const PlusDeco = ({ style, color = 'rgba(255,255,255,0.5)' }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" style={style} className="lp-deco" aria-hidden="true">
    <path d="M8 1v14M1 8h14" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
  </svg>
)

const REVEAL_SELECTOR = [
  '.lp-chip', '.lp-h2', '.lp-underline',
  '.lp-paso',
  '.lp-beneficios-col', '.lp-beneficios-box',
  '.lp-video-card',
  '.lp-kits-intro', '.lp-pagos', '.lp-card', '.lp-oferta',
  '.lp-quienes-foto', '.lp-quienes-texto',
  '.lp-testimonio',
  '.lp-club-visual', '.lp-club-texto',
  '.lp-ganador', '.lp-convocatoria-texto', '.lp-convocatoria-visual',
  '.lp-faq-item',
  '.lp-contacto-info', '.lp-contacto-form',
  // Marcador neutro, sin estilos propios: lo usan las pantallas nuevas para
  // pedir el revelado sin tener que colgarse de una clase que además pinta
  // (como .lp-card, que trae el padding y el radio de las tarjetas de kits).
  '.lp-anim',
].join(',')

export function useScrollReveal(rootRef, deps = []) {
  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const noIO = typeof IntersectionObserver === 'undefined'

    // Elementos aún no revelados; se ignoran los que están dentro de otro a
    // revelar (basta animar el contenedor). `revealDone` = ya visible;
    // `revealArmed` = ya se le puso opacity:0 (no re-armar en cada corrida).
    const all = Array.from(root.querySelectorAll(REVEAL_SELECTOR))
    const pending = all.filter(el =>
      !el.dataset.revealDone &&
      !all.some(other => other !== el && other.contains(el))
    )

    // Sin animación posible (reduced-motion o sin IntersectionObserver):
    // mostrar todo de inmediato. NUNCA dejar contenido oculto.
    if (reduce || noIO) {
      pending.forEach(el => { el.classList.add('lp-in'); el.dataset.revealDone = '1' })
      return
    }

    // Ocultar una sola vez y preparar el stagger entre hermanos.
    const perParent = new Map()
    pending.forEach(el => {
      if (el.dataset.revealArmed) return
      const i = perParent.get(el.parentElement) || 0
      perParent.set(el.parentElement, i + 1)
      el.style.transitionDelay = `${Math.min(i, 6) * 80}ms`
      el.classList.add('lp-reveal')
      el.dataset.revealArmed = '1'
    })

    // Observer NUEVO en cada corrida, desconectado en su propio cleanup: así el
    // doble montaje de StrictMode (montar→desmontar→montar) vuelve a observar y
    // el contenido nunca queda atascado en opacity:0.
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('lp-in')
          entry.target.dataset.revealDone = '1'
          io.unobserve(entry.target)
        }
      }
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' })

    pending.forEach(el => io.observe(el))

    // Red de seguridad: si el observer no revela algo que YA debería verse
    // (arriba del borde inferior del viewport), se muestra igual. Lo de más
    // abajo sigue entrando con animación al hacer scroll.
    const failSafe = window.setTimeout(() => {
      const vh = window.innerHeight
      root.querySelectorAll('.lp-reveal:not(.lp-in)').forEach(el => {
        if (el.getBoundingClientRect().top < vh) {
          el.classList.add('lp-in')
          el.dataset.revealDone = '1'
          io.unobserve(el)
        }
      })
    }, 1200)

    return () => { window.clearTimeout(failSafe); io.disconnect() }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
}
