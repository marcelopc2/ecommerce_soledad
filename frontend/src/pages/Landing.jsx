import { useState, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Contacto, LandingFooter } from '../components/LandingSections'
import './landing.css'

import logo from '../assets/landing/logo-ingenioblocks.svg'
import heroNino from '../assets/landing/hero-nino.png'
import pagosBadges from '../assets/landing/pagos-badges.svg'
import quienesSomosNino from '../assets/landing/quienes-somos-nino.png'
import concurso3d from '../assets/landing/concurso-3d.png'

/* ---------- Datos estructurados (SEO) ----------
   La cuadrícula de FAQ y los productos vienen de la API, así que su JSON-LD se
   arma en el cliente (Googlebot ejecuta JavaScript y lo lee; los crawlers de
   redes sociales no, pero para ellos ya están las etiquetas Open Graph fijas
   del index.html). El FAQPage puede hacer que las preguntas salgan desplegables
   en los resultados de Google. */
const SITE_URL = (import.meta.env.VITE_SITE_URL || '').replace(/\/$/, '')

function useJsonLd(id, data) {
  useEffect(() => {
    if (!data) return
    const el = document.createElement('script')
    el.type = 'application/ld+json'
    el.id = id
    el.textContent = JSON.stringify(data)
    document.head.appendChild(el)
    return () => { el.remove() }
  }, [id, data])
}

/* ---------- Iconos SVG inline ---------- */

const IconCart = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="9" cy="21" r="1.5" /><circle cx="19" cy="21" r="1.5" />
    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
  </svg>
)

const IconUser = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
  </svg>
)

const IconPlayCircle = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" />
  </svg>
)

const IconPlaySolid = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="#2f0053"><polygon points="8 5 19 12 8 19 8 5" /></svg>
)

const IconCheck = ({ color = '#00a63e' }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="11" fill={color} opacity="0.15" />
    <path d="M7 12.5l3.2 3.2L17 9" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
  </svg>
)

const IconStar = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="#ffba00">
    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
  </svg>
)







const Sparkle = ({ size = 20, color = '#ffcb00', style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} style={style} className="lp-deco" aria-hidden="true">
    <path d="M12 0c.6 6.5 5.5 11.4 12 12-6.5.6-11.4 5.5-12 12-.6-6.5-5.5-11.4-12-12C6.5 11.4 11.4 6.5 12 0z" />
  </svg>
)

const PlusDeco = ({ style, color = 'rgba(255,255,255,0.5)' }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" style={style} className="lp-deco" aria-hidden="true">
    <path d="M8 1v14M1 8h14" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
  </svg>
)

const ChevronsRight = () => (
  <svg width="66" height="52" viewBox="0 0 33 26" fill="none" stroke="#dfe3ea" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline className="lp-chevron lp-chevron-1" points="4 3 14 13 4 23" />
    <polyline className="lp-chevron lp-chevron-2" points="18 3 28 13 18 23" />
  </svg>
)

/* ---------- Datos estáticos del diseño ---------- */

// Carrito: el offset de centrado NO se adivinó a ojo — se midió el centroide
// real de los píxeles blancos renderizados (script aparte con resvg) contra el
// centro real del círculo de 40px, e iteró hasta quedar en ~0% de desvío.
// La canasta pesa más que el mango, así que el ajuste correcto es hacia la
// IZQUIERDA (un intento anterior lo corrió a la derecha, empeorándolo).
const IconoPasoKit = () => (
  <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'translate(-0.3px, -0.5px)' }}>
    <circle cx="10" cy="20" r="1.5" />
    <circle cx="17.5" cy="20" r="1.5" />
    <path d="M4 4h2.3l2 10.4a1.7 1.7 0 0 0 1.7 1.4h6.6a1.7 1.7 0 0 0 1.7-1.3L20 7.5H7" />
  </svg>
)
const IconoPasoAula = () => (
  <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.5" y="4" width="19" height="13" rx="2.2" />
    <path d="M8.5 21h7M12 17.5v3.5" />
  </svg>
)
// Mando de videojuego (paso "juega y disfruta"): agrandado — la versión anterior
// medía solo 25% del alto del círculo (vs ~42% del carrito) y se veía enano al
// lado de los otros dos íconos aunque tuviera tinta similar, por ser un cuerpo
// muy chato. Ahora el cuerpo es más alto y los botones más grandes; centrado
// con el mismo método de centroide medido que el carrito.
const IconoPasoJuega = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'translate(0.16px, -0.48px)' }}>
    <rect x="2" y="7" width="20" height="12" rx="6" />
    <path d="M7.5 11v4M5.5 13h4" />
    <circle cx="16" cy="11.3" r="1.15" fill="currentColor" stroke="none" />
    <circle cx="18.6" cy="13.9" r="1.15" fill="currentColor" stroke="none" />
  </svg>
)

// Los íconos son SVG del diseño, no imágenes subibles: el panel solo guarda
// cuál corresponde a cada paso (campo `icon`) y acá se resuelve al componente.
const ICONOS_PASO = {
  kit: <IconoPasoKit />,
  aula: <IconoPasoAula />,
  juega: <IconoPasoJuega />,
}


const KIT_DESC = 'Kit de bloques Ingenio Blocks con más de 400 piezas + motor y batería, que permite construir más de 100 modelos.'

/* ---------- Secciones ---------- */

const SECCIONES_NAV = [
  ['como-funciona', 'Cómo funciona'],
  ['beneficios', 'Beneficios'],
  ['kits', 'Kits'],
  ['quienes-somos', 'Quiénes somos'],
  ['contacto', 'Contacto'],
]

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

function LandingHeader({ active }) {
  const { user } = useAuth()
  const [menuAbierto, setMenuAbierto] = useState(false)
  const cls = (id) => (active === id ? 'active' : undefined)

  // Mientras el menú está abierto se bloquea el scroll del fondo y Escape lo
  // cierra, igual que el modal de video.
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

  return (
    <header className="lp-header">
      <Link to="/" className="lp-logo"><img src={logo} alt="Ingenio Blocks" /></Link>

      <nav className="lp-nav">
        {SECCIONES_NAV.map(([id, texto]) => (
          <a key={id} href={`#${id}`} className={cls(id)}>{texto}</a>
        ))}
      </nav>

      <div className="lp-header-right">
        <Link to="/#kits" className="lp-cart" aria-label="Ver los kits"><IconCart /></Link>
        <span className="lp-header-divider" />
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
            {SECCIONES_NAV.map(([id, texto]) => (
              <a key={id} href={`#${id}`} className={cls(id)}
                 onClick={() => setMenuAbierto(false)}>{texto}</a>
            ))}
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

function Hero({ activeSection }) {
  return (
    <section className="lp-hero">
      <div className="lp-hero-grid" aria-hidden="true" />
      <LandingHeader active={activeSection} />
      <div className="lp-hero-inner">
        <div className="lp-hero-copy">
          <span className="lp-chip lp-chip-hero">⚡ despierta su ingenio</span>
          <h1>
            la <span className="lp-yellow">experiencia</span> de construcción diseñada
            para explorar, crear, aprender y avanzar.
          </h1>
          <p>
            Con nuestro kit de bloques de más de 400 piezas, los niños pueden acceder
            a más de 100 modelos motorizados con instrucciones paso a paso a través
            de nuestra Aula Virtual.
          </p>
          <a href="#kits" className="lp-btn-yellow lp-btn-cta">comprar ahora</a>
        </div>
        <div className="lp-hero-photo">
          <img src={heroNino} alt="Niño construyendo con bloques Ingenio Blocks" />
        </div>
      </div>
      {/* decoraciones flotantes */}
      <Sparkle size={26} style={{ top: '17%', right: '3.5%', '--dur': '5s' }} />
      <Sparkle size={22} color="rgba(255,255,255,0.7)" style={{ top: '48%', left: '39%', '--dur': '7s', '--delay': '1.2s' }} />
      <Sparkle size={16} style={{ top: '70%', left: '12%', '--dur': '6s', '--delay': '0.5s' }} />
      <Sparkle size={18} color="rgba(255,255,255,0.55)" style={{ top: '12%', left: '30%', '--dur': '8s', '--delay': '2s' }} />
      <PlusDeco style={{ top: '21%', left: '9%', '--dur': '9s' }} />
      <PlusDeco style={{ top: '48%', right: '4%', '--dur': '6.5s', '--delay': '1.8s' }} color="rgba(255,203,0,0.7)" />
      <PlusDeco style={{ top: '62%', left: '61%', '--dur': '7.5s', '--delay': '0.8s' }} />
      <PlusDeco style={{ top: '82%', left: '28%', '--dur': '8.5s', '--delay': '2.4s' }} color="rgba(255,203,0,0.55)" />
      <PlusDeco style={{ top: '9%', right: '22%', '--dur': '10s', '--delay': '1s' }} />
      <svg className="lp-deco" width="20" height="20" viewBox="0 0 20 20" style={{ top: '43%', left: '2.5%', '--dur': '7s' }} aria-hidden="true">
        <polygon points="3,2 17,10 3,18" fill="#ffcb00" />
      </svg>
      <svg className="lp-deco" width="14" height="14" viewBox="0 0 20 20" style={{ top: '26%', left: '55%', '--dur': '9s', '--delay': '3s' }} aria-hidden="true">
        <polygon points="3,2 17,10 3,18" fill="rgba(255,255,255,0.5)" transform="rotate(120 10 10)" />
      </svg>
      <span className="lp-deco lp-deco-dot" style={{ top: '20%', left: '52%', '--dur': '6s' }} aria-hidden="true" />
      <span className="lp-deco lp-deco-dot" style={{ top: '74%', left: '3%', '--dur': '8s', '--delay': '1.5s' }} aria-hidden="true" />
      <span className="lp-deco lp-deco-dot lp-deco-dot-yellow" style={{ top: '34%', right: '46%', '--dur': '7s', '--delay': '2.2s' }} aria-hidden="true" />
    </section>
  )
}

function ComoFunciona() {
  const [pasos, setPasos] = useState([])

  useEffect(() => {
    api.get('/catalog/landing-steps/')
      .then(res => setPasos(res.data))
      .catch(() => {}) // la landing funciona igual sin los pasos
  }, [])

  return (
    <section className="lp-como" id="como-funciona">
      <span className="lp-chip lp-chip-lila">la experiencia</span>
      <h2 className="lp-h2">cómo funciona</h2>
      <span className="lp-underline" />
      <div className="lp-pasos">
        {pasos.map((paso, i) => (
          <div className="lp-paso" key={paso.id}>
            <div className="lp-paso-foto" style={{ '--tilt-color': paso.color }}>
              {paso.photo_url && <img src={paso.photo_url} alt={paso.title} />}
            </div>
            <div className="lp-paso-body">
              {/* El número sale de la posición, no de la BD: si la clienta
                  borra un paso intermedio, la numeración no queda saltada. */}
              <span className="lp-paso-num">{String(i + 1).padStart(2, '0')}</span>
              <span className="lp-paso-dot" style={{ background: paso.color }}>
                {ICONOS_PASO[paso.icon] ?? ICONOS_PASO.kit}
              </span>
              <h3>{paso.title}</h3>
              <p>{paso.description}</p>
              {i < pasos.length - 1 && <span className="lp-paso-arrow"><ChevronsRight /></span>}
            </div>
          </div>
        ))}
      </div>
      <a href="#beneficios" className="lp-btn-yellow lp-btn-cta lp-btn-play">
        ¿cómo empezar a construir? <IconPlayCircle />
      </a>
    </section>
  )
}

// Modal con el reproductor de YouTube. Se monta en document.body (portal) para
// que ningún transform/contexto de apilamiento de la landing lo afecte.
function VideoModal({ video, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'  // bloquea el scroll del fondo
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return createPortal(
    <div className="lp-vmodal" onClick={onClose}>
      <div className="lp-vmodal-inner" onClick={(e) => e.stopPropagation()}>
        <button className="lp-vmodal-close" onClick={onClose} aria-label="Cerrar video">×</button>
        <div className="lp-vmodal-frame">
          <iframe
            src={`https://www.youtube.com/embed/${video.youtube_id}?autoplay=1&rel=0`}
            title={video.title}
            allow="autoplay; encrypted-media; fullscreen"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}

function Beneficios() {
  const [videos, setVideos] = useState([])
  const [activeVideo, setActiveVideo] = useState(null)

  useEffect(() => {
    api.get('/catalog/landing-videos/')
      .then(res => setVideos(res.data))
      .catch(() => {}) // la landing funciona igual sin videos
  }, [])

  // Rotación aleatoria por tarjeta. Se calcula recién cuando llegan los videos
  // (antes el array venía fijo del código y se podía sembrar en el useState
  // inicial); useMemo la deja estable entre re-renders para que la tarjeta no
  // cambie de inclinación en cada hover.
  const rotations = useMemo(
    () => videos.map(() => (Math.random() * 6 - 3).toFixed(2)),
    [videos.length],
  )

  return (
    <section className="lp-beneficios" id="beneficios">
      <div className="lp-beneficios-col">
        <span className="lp-chip lp-chip-lila">descubre el contenido</span>
        <h2 className="lp-h2">beneficios</h2>
        <span className="lp-underline" style={{ margin: '0 0 28px' }} />
        <div className="lp-beneficios-texto">
          <p>
            En un mundo en constante evolución, la educación tradicional enfrenta un
            gran desafío: adaptarse. Porque los niños ya no aprenden solo escuchando,
            sino haciendo, creando y resolviendo.
          </p>
          <p>
            <strong className="lp-purple-text">Ingenio Blocks</strong> es una Plataforma
            educativa que combina el juego con el aprendizaje práctico. Con nuestro kit
            de bloques de más de 400 piezas, los niños pueden acceder a más de 100
            modelos motorizados —uno nuevo cada semana— con instrucciones paso a paso
            a través de nuestra Aula Virtual.
          </p>
          <p>
            Nuestra Plataforma está diseñada en un formato amigable que permite a{' '}
            <strong>niños y niñas desde los 6 años</strong>, sumergirse fácilmente en
            emocionantes talleres desarrollados con metodologías de aprendizaje en
            espiral. Esto significa que podrán avanzar a su propio ritmo.
          </p>
        </div>
      </div>
      <div className="lp-beneficios-box">
        <div className="lp-studs" aria-hidden="true">
          {Array.from({ length: 10 }).map((_, i) => <span key={i} />)}
        </div>
        <h3>Sobre el Mundo Ingenio Blocks</h3>
        <p className="lp-beneficios-box-intro">
          Como parte de nuestra metodología, cada modelo plantea un nuevo desafío,
          aumentando gradualmente en dificultad para fortalecer habilidades cognitivas,
          motoras y sociales. Cada Proyecto está diseñado para explorar, crear, aprender
          y avanzar en temas que abarcan desde los ecosistemas hasta las fuerzas que
          dirigen y hacen funcionar vehículos y artefactos motorizados.{' '}
          <strong>Algunos de nuestros modelos:</strong>
        </p>
        <div className="lp-videos">
          {videos.map((v, i) => (
            <button
              type="button"
              className="lp-video-card"
              key={v.id}
              style={{ '--hover-rot': `${rotations[i]}deg` }}
              onClick={() => setActiveVideo(v)}
              aria-label={`Reproducir video: ${v.title}`}
            >
              <div className="lp-video-thumb">
                {v.cover_url && <img src={v.cover_url} alt={v.title} />}
                <span className="lp-video-play"><IconPlaySolid /></span>
              </div>
              <div className="lp-video-body">
                <h4>{v.title}</h4>
                <p>{v.description}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
      {activeVideo && <VideoModal video={activeVideo} onClose={() => setActiveVideo(null)} />}
    </section>
  )
}

const money = (n) => `$${parseInt(n, 10).toLocaleString('es-CL')}`

// Precio: muestra el de oferta (rojo + tachado el normal) o el normal con su nota.
function PriceBlock({ product, extraClass = '' }) {
  const onSale = product.is_on_sale && product.sale_price != null
  return (
    <div className={'lp-price-box ' + extraClass}>
      {onSale ? (
        <>
          <span className="lp-price lp-price-red">{money(product.sale_price)}</span>
          <span className="lp-price-antes">antes <s>{money(product.price)}</s></span>
        </>
      ) : (
        <>
          <span className="lp-price">{money(product.price)}</span>
          {product.price_note && <span className="lp-price-note">{product.price_note}</span>}
        </>
      )}
    </div>
  )
}

// Ribbon: prioriza "Próximamente"; si no, "Oferta" cuando está en oferta.
function CardRibbon({ product }) {
  if (product.is_coming_soon) return <span className="lp-ribbon">Próximamente</span>
  if (product.is_on_sale) return <span className="lp-ribbon lp-ribbon-red">Oferta</span>
  return null
}

// Tarjeta normal (las 3 de la grilla)
function KitCard({ product, onBuy }) {
  const { user } = useAuth()
  const soon = product.is_coming_soon
  const needsLogin = product.requires_login && !user
  const purple = product.highlight
  const hasRibbon = product.is_coming_soon || product.is_on_sale
  return (
    <article className={'lp-card' + (purple ? ' lp-card-purple' : '')}>
      <CardRibbon product={product} />
      <div className={'lp-card-top' + (hasRibbon ? ' has-ribbon' : '')}>
        {product.landing_badge && (
          <span className={'lp-chip ' + (purple ? 'lp-chip-mensual' : 'lp-chip-pago')}>
            {product.landing_badge}
          </span>
        )}
      </div>
      <h3>{product.name}</h3>
      <p className="lp-card-desc">{product.description}</p>
      <ul className={'lp-checks' + (purple ? ' lp-checks-yellow' : '')}>
        {product.features_list.map((f, i) => (
          <li key={i}><IconCheck color={purple ? '#ffcb00' : undefined} /> {f}</li>
        ))}
      </ul>
      <div className="lp-card-footer">
        <PriceBlock product={product} />
        <button className="lp-btn-yellow lp-btn-cta lp-btn-card" disabled={soon} onClick={() => onBuy(product)}>
          {soon ? 'Próximamente' : needsLogin ? 'inicia sesión para comprar' : `comprar ${product.name}`}
        </button>
      </div>
    </article>
  )
}

// Tarjeta ancha de abajo (el 4º producto, opcional)
function KitWide({ product, onBuy }) {
  const { user } = useAuth()
  const soon = product.is_coming_soon
  const needsLogin = product.requires_login && !user
  return (
    <article className="lp-oferta">
      <CardRibbon product={product} />
      <div className="lp-oferta-head">
        <h3>{product.name}</h3>
        {product.landing_badge && <span className="lp-chip lp-chip-pago">{product.landing_badge}</span>}
        <p className="lp-card-desc">{product.description}</p>
      </div>
      <ul className="lp-checks lp-oferta-checks">
        {product.features_list.map((f, i) => <li key={i}><IconCheck /> {f}</li>)}
      </ul>
      <div className="lp-oferta-buy">
        <PriceBlock product={product} extraClass="lp-oferta-price" />
        <button className="lp-btn-yellow lp-btn-cta lp-btn-card" disabled={soon} onClick={() => onBuy(product)}>
          {soon ? 'Próximamente' : needsLogin ? 'inicia sesión para comprar' : `comprar ${product.name}`}
        </button>
      </div>
    </article>
  )
}

function Kits({ products }) {
  const navigate = useNavigate()
  const { user } = useAuth()

  const comprar = (product) => {
    if (!product || product.is_coming_soon) return
    // Packs/planes solo para alumnos: primero inicia sesión y después vuelve al
    // checkout con el producto. El servidor igual lo revalida (requires_login).
    if (product.requires_login && !user) {
      navigate('/login', { state: { from: '/checkout', checkoutProduct: product } })
      return
    }
    navigate('/checkout', { state: { product } })
  }

  // productos de la portada: hasta 4, ordenados; 3 en grilla + 1 ancho abajo
  const landing = products
    .filter(p => p.show_on_landing)
    .sort((a, b) => (a.landing_order - b.landing_order) || (a.id - b.id))
    .slice(0, 4)
  const grid = landing.slice(0, 3)
  const wide = landing[3]

  return (
    <section className="lp-kits" id="kits">
      <h2 className="lp-h2 lp-h2-white">nuestros kits</h2>
      <span className="lp-underline" />
      <p className="lp-kits-intro">
        Te invitamos a hacerte parte del Mundo Ingenio Blocks y comenzar a disfrutar de
        esta divertida forma de aprender a través de nuestros talleres virtuales, con más
        de 100 modelos motorizados. ¡Explora y crea un modelo diferente cada semana!
      </p>
      <img className="lp-pagos" src={pagosBadges} alt="Pagos 100% seguros: Webpay, MercadoPago, Visa, Mastercard, Redcompra" />

      {grid.length > 0 && (
        <div className="lp-cards">
          {grid.map(p => <KitCard key={p.id} product={p} onBuy={comprar} />)}
        </div>
      )}
      {wide && <KitWide product={wide} onBuy={comprar} />}
    </section>
  )
}

function QuienesSomos() {
  return (
    <section className="lp-quienes" id="quienes-somos">
      <span className="lp-chip lp-chip-lila">sobre el equipo</span>
      <h2 className="lp-h2">quiénes somos</h2>
      <span className="lp-underline" />
      <div className="lp-quienes-inner">
        <div className="lp-quienes-foto">
          <span className="lp-circle-dotted" aria-hidden="true" />
          <span className="lp-circle-gray" aria-hidden="true" />
          <span className="lp-circle-yellow" aria-hidden="true" />
          <span className="lp-circle-purple" aria-hidden="true" />
          <img src={quienesSomosNino} alt="Niño construyendo un modelo motorizado" />
        </div>
        <div className="lp-quienes-texto">
          <p>
            En Ingenio Blocks somos un equipo que cree en el poder transformador del
            aprendizaje práctico y entretenido. Con más de una década de experiencia en
            el mundo de la formación corporativa, hoy también ofrecemos a{' '}
            <strong className="lp-purple-text">niños y jóvenes desde los 6 años</strong>{' '}
            una experiencia educativa única a través de la construcción con bloques.
          </p>
          <p>
            Nuestro enfoque innovador se basa en la idea de que las habilidades
            fundamentales para los futuros profesionales pueden y deben desarrollarse
            desde temprana edad. A través de actividades lúdicas y proyectos prácticos,
            nuestros estudiantes no solo aprenden principios esenciales de matemáticas,
            física y mecánica, sino que también cultivan su creatividad, pensamiento
            crítico y capacidad para resolver problemas.
          </p>
          <p>
            Creemos que el aprendizaje debe ser una aventura emocionante. Es por eso que
            cada una de nuestras sesiones está diseñada para inspirar y desafiar a
            nuestros jóvenes alumnos, fomentando la libertad de explorar, experimentar y
            descubrir el mundo que les rodea.
          </p>
        </div>
      </div>
    </section>
  )
}

function Testimonios() {
  const [testimonials, setTestimonials] = useState([])

  useEffect(() => {
    api.get('/catalog/testimonials/')
      .then(res => setTestimonials(res.data))
      .catch(() => {}) // la landing funciona igual sin testimonios
  }, [])

  return (
    <section className="lp-testimonios">
      <span className="lp-chip lp-chip-lila">comunidad feliz</span>
      <h2 className="lp-h2">testimonios</h2>
      <span className="lp-underline" />
      <div className="lp-testimonios-grid">
        {testimonials.map((t) => (
          <article className="lp-testimonio" key={t.id}>
            <div className="lp-testimonio-in">
              <div className="lp-stars">
                {Array.from({ length: t.rating }).map((_, j) => <IconStar key={j} />)}
              </div>
              <span className="lp-quote" aria-hidden="true">“</span>
              <p>"{t.quote}"</p>
              <footer>
                <strong>{t.name}</strong>
                <span>{t.location}</span>
              </footer>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

// Texto real del concurso. Mientras esté vacío la sección NO se muestra: iba a
// producción con "Lorem ipsum dolor sit amet...", que es lo peor que puede leer
// alguien a punto de gastar decenas de miles de pesos. No se inventa un texto
// acá porque implicaría afirmar cosas de un concurso (premios, fechas, bases)
// que solo la clienta puede definir. Con pegar el texto aquí vuelve a aparecer.
const TEXTO_CONCURSO = ''

function Concurso({ texto }) {
  return (
    <section className="lp-concurso-band">
      <div className="lp-concurso">
        <div className="lp-concurso-visual">
          <span className="lp-concurso-brand">Ingenio<br />Blocks</span>
          <img src={concurso3d} alt="Trofeo Ingenio Blocks en 3D" />
        </div>
        <div className="lp-concurso-texto">
          <span className="lp-chip lp-chip-lila">ganador del año</span>
          <h2 className="lp-h2">concurso</h2>
          <span className="lp-underline" style={{ margin: '0 0 24px' }} />
          <p>{texto}</p>
        </div>
      </div>
    </section>
  )
}

function Faq() {
  const [faqs, setFaqs] = useState([])
  const [open, setOpen] = useState(-1)
  const [verMas, setVerMas] = useState(false)

  useEffect(() => {
    api.get('/catalog/faqs/')
      .then(res => setFaqs(res.data))
      .catch(() => {}) // la landing funciona igual sin preguntas frecuentes
  }, [])

  // FAQPage: le da a Google las preguntas y respuestas en un formato que puede
  // mostrar desplegable directo en los resultados.
  useJsonLd('ld-faq', useMemo(() => (faqs.length ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map(f => ({
      '@type': 'Question',
      name: f.question,
      acceptedAnswer: { '@type': 'Answer', text: f.answer },
    })),
  } : null), [faqs]))

  const visibles = verMas ? faqs : faqs.slice(0, 6)

  return (
    <section className="lp-faq">
      <span className="lp-chip lp-chip-lila">resuelve tus dudas</span>
      <h2 className="lp-h2">Preguntas Frecuentes</h2>
      <span className="lp-underline" />
      <div className="lp-faq-list">
        {visibles.map((f, i) => (
          <div className={`lp-faq-item${open === i ? ' open' : ''}`} key={f.id}>
            <button className="lp-faq-q" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
              <span>{f.question}</span>
              <span className="lp-faq-toggle" aria-hidden="true" />
            </button>
            <div className="lp-faq-a-wrap">
              <div className="lp-faq-a">{f.answer}</div>
            </div>
          </div>
        ))}
      </div>
      {!verMas && faqs.length > 6 && (
        <button className="lp-vermas" onClick={() => setVerMas(true)}>ver más</button>
      )}
    </section>
  )
}

const REVEAL_SELECTOR = [
  '.lp-chip', '.lp-h2', '.lp-underline',
  '.lp-paso',
  '.lp-beneficios-col', '.lp-beneficios-box',
  '.lp-video-card',
  '.lp-kits-intro', '.lp-pagos', '.lp-card', '.lp-oferta',
  '.lp-quienes-foto', '.lp-quienes-texto',
  '.lp-testimonio',
  '.lp-concurso-visual', '.lp-concurso-texto',
  '.lp-faq-item',
  '.lp-contacto-info', '.lp-contacto-form',
].join(',')

function useScrollReveal(rootRef, deps = []) {
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

export default function Landing() {
  const [activeSection, setActiveSection] = useState('')
  const [products, setProducts] = useState([])
  const rootRef = useRef(null)
  const location = useLocation()
  // re-escanea el reveal cuando llegan los productos (cards asíncronas)
  useScrollReveal(rootRef, [products.length])

  useEffect(() => {
    api.get('/catalog/products/')
      .then(res => setProducts(res.data))
      .catch(() => {}) // la landing funciona igual sin catálogo
  }, [])

  // Cada kit como Product de Schema.org, con su precio. Ayuda a Google a
  // entender que es una tienda y puede mostrar el precio en el resultado.
  useJsonLd('ld-products', useMemo(() => {
    const vendibles = products.filter(p => !p.is_coming_soon)
    if (!vendibles.length) return null
    return {
      '@context': 'https://schema.org',
      '@type': 'ItemList',
      itemListElement: vendibles.map((p, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        item: {
          '@type': 'Product',
          name: p.name,
          description: p.description || undefined,
          brand: { '@type': 'Brand', name: 'Ingenio Blocks' },
          offers: {
            '@type': 'Offer',
            price: parseInt(p.effective_price ?? p.price, 10),
            priceCurrency: 'CLP',
            availability: 'https://schema.org/InStock',
            url: `${SITE_URL}/#kits`,
          },
        },
      })),
    }
  }, [products]))

  // Los <a href="#kits"> normales solo saltan al ancla si ya estamos en "/"
  // (es scroll nativo del navegador). Si el link viene de otra página con
  // <Link to="/#kits">, React Router cambia de ruta pero NO hace ese scroll
  // solo -queda arriba de todo-, así que hay que hacerlo a mano acá.
  useEffect(() => {
    if (!location.hash) return
    const id = location.hash.slice(1)
    // rAF: espera a que el layout de la sección ya esté pintado (ids como
    // "kits" dependen de contenido que puede tardar un frame en montarse).
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    })
  }, [location.hash])

  // scrollspy: marca en el navbar la última sección cuyo inicio pasó el 40% del viewport
  useEffect(() => {
    const ids = ['como-funciona', 'beneficios', 'kits', 'quienes-somos', 'contacto']
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const line = window.innerHeight * 0.4
        let current = ''
        for (const id of ids) {
          const el = document.getElementById(id)
          if (el && el.getBoundingClientRect().top <= line) current = id
        }
        setActiveSection(current)
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    onScroll()
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  return (
    <div className="lp" ref={rootRef}>
      <Hero activeSection={activeSection} />
      <ComoFunciona />
      <Beneficios />
      <Kits products={products} />
      <QuienesSomos />
      <Testimonios />
      {TEXTO_CONCURSO && <Concurso texto={TEXTO_CONCURSO} />}
      <Faq />
      <Contacto />
      <LandingFooter />
    </div>
  )
}
