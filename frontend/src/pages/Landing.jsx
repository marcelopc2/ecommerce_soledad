import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import './landing.css'

import logo from '../assets/landing/logo-ingenioblocks.svg'
import heroNino from '../assets/landing/hero-nino.png'
import paso1 from '../assets/landing/paso1.png'
import paso2 from '../assets/landing/paso2.png'
import paso3 from '../assets/landing/paso3.png'
import videoTaladro from '../assets/landing/video-taladro.png'
import videoCaleidoscopio from '../assets/landing/video-caleidoscopio.png'
import videoCentrifuga from '../assets/landing/video-centrifuga.png'
import pagosBadges from '../assets/landing/pagos-badges.svg'
import quienesSomosNino from '../assets/landing/quienes-somos-nino.png'
import concurso3d from '../assets/landing/concurso-3d.png'

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
  <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#e2e8f0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 5 13 12 6 19" /><polyline points="13 5 20 12 13 19" />
  </svg>
)

/* Sticker "Recomendado desde los 6 años" */
const StickerBadge = () => (
  <div className="lp-sticker">
    <svg viewBox="0 0 150 150" width="150" height="150">
      <polygon
        points="75.0,1.0 88.8,14.6 107.1,8.3 113.7,26.5 132.9,28.9 130.9,48.1 147.1,58.5 137.0,75.0 147.1,91.5 130.9,101.9 132.9,121.1 113.7,123.5 107.1,141.7 88.8,135.4 75.0,149.0 61.2,135.4 42.9,141.7 36.3,123.5 17.1,121.1 19.1,101.9 2.9,91.5 13.0,75.0 2.9,58.5 19.1,48.1 17.1,28.9 36.3,26.5 42.9,8.3 61.2,14.6"
        fill="#ffcb00" stroke="#f0b100" strokeWidth="2" strokeLinejoin="round"
      />
    </svg>
    <span><em>Recomendado para niños y niñas desde los <strong>6 años</strong></em></span>
  </div>
)

/* ---------- Datos estáticos del diseño ---------- */

const PASOS = [
  {
    num: '01', color: '#6a3093', foto: paso1,
    titulo: 'Adquiere tu Kit Ingenio Blocks',
    texto: 'Recibe en casa tu set de bloques físicos de alta calidad y prepárate para abrir la puerta a un mundo de creatividad tangible para tu hijo.',
  },
  {
    num: '02', color: '#00a63e', foto: paso2,
    titulo: 'Ingresa a nuestra Aula Virtual',
    texto: 'Desbloquea tu acceso exclusivo a la plataforma interactiva. Encuentra cientos de guías visuales paso a paso, retos divertidos y proyectos nuevos que se actualizan constantemente.',
  },
  {
    num: '03', color: '#ff6101', foto: paso3,
    titulo: 'Juega y disfruta',
    texto: 'Observa cómo tu pequeño da vida a sus propias ideas. Aprende jugando de forma autónoma, fomenta su concentración y desarrolla habilidades clave mientras se divierte.',
  },
]

const VIDEOS = [
  {
    foto: videoTaladro, titulo: 'Taladro y Herramientas',
    texto: 'Aprende cómo un motor convierte la energía eléctrica en movimiento que permite hacer girar una broca de taladro.',
  },
  {
    foto: videoCaleidoscopio, titulo: 'Caleidoscopio',
    texto: '¡Explora el maravilloso mundo de la óptica y la creatividad, donde cada giro revela una nueva y deslumbrante combinación de colores y formas!',
  },
  {
    foto: videoCentrifuga, titulo: 'Centrífuga de Ropa',
    texto: 'Descubre cómo este ingenioso mecanismo transforma la tarea de lavar en un proceso rápido y eficiente.',
  },
]

const KIT_DESC = 'Kit de bloques Ingenio Blocks con más de 400 piezas + motor y batería, que permite construir más de 100 modelos.'

const FAQS = [
  {
    q: '¿Qué es Ingenio Blocks?',
    a: 'Ingenio Blocks es una plataforma educativa que combina la entretención con el aprendizaje práctico. Con nuestro kit educativo STEM que contiene más de 400 piezas (bloques) + motor y batería y acceso a nuestra plataforma, los niños desde los 6 años pueden acceder a más de 100 modelos motorizados —uno nuevo cada semana— con instrucciones paso a paso.',
  },
  {
    q: '¿Qué aprenden los niños con Ingenio Blocks?',
    a: 'A través de la construcción de modelos motorizados, los niños aprenden principios esenciales de matemáticas, física y mecánica, mientras cultivan su creatividad, pensamiento crítico y capacidad para resolver problemas.',
  },
  {
    q: '¿Qué edad deben tener los participantes?',
    a: 'Nuestra plataforma está diseñada para niños y niñas desde los 6 años. El formato amigable les permite avanzar a su propio ritmo.',
  },
  {
    q: '¿Cómo funcionan los programas?',
    a: 'Al adquirir tu kit, obtienes acceso a nuestra Aula Virtual, donde cada semana se libera un nuevo modelo motorizado con instrucciones paso a paso. Cada modelo plantea un nuevo desafío, aumentando gradualmente en dificultad.',
  },
  {
    q: '¿Qué tipo de metodología de aprendizaje usa Ingenio Blocks?',
    a: 'Usamos metodologías de aprendizaje en espiral: cada proyecto está diseñado para explorar, crear, aprender y avanzar, fortaleciendo habilidades cognitivas, motoras y sociales.',
  },
  {
    q: '¿Es necesario tener conocimientos previos en robótica o programación?',
    a: 'No, no se requiere ningún conocimiento previo. Las instrucciones paso a paso permiten que cualquier niño comience a construir desde el primer día.',
  },
]

/* ---------- Secciones ---------- */

function LandingHeader({ active }) {
  const { user } = useAuth()
  const cls = (id) => (active === id ? 'active' : undefined)
  return (
    <header className="lp-header">
      <Link to="/" className="lp-logo"><img src={logo} alt="Ingenio Blocks" /></Link>
      <nav className="lp-nav">
        <a href="#como-funciona" className={cls('como-funciona')}>Cómo funciona</a>
        <a href="#beneficios" className={cls('beneficios')}>Beneficios</a>
        <a href="#kits" className={cls('kits')}>Kits</a>
        <a href="#quienes-somos" className={cls('quienes-somos')}>Quiénes somos</a>
        <a href="#contacto" className={cls('contacto')}>Contacto</a>
      </nav>
      <div className="lp-header-right">
        <Link to="/tienda" className="lp-cart" aria-label="Tienda"><IconCart /></Link>
        <span className="lp-header-divider" />
        {user ? (
          <Link to="/mis-cursos" className="lp-login-btn">mis cursos <IconUser /></Link>
        ) : (
          <Link to="/login" className="lp-login-btn">iniciar sesión <IconUser /></Link>
        )}
      </div>
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
          <a href="#kits" className="lp-btn-yellow">comprar ahora</a>
        </div>
        <div className="lp-hero-photo">
          <img src={heroNino} alt="Niño construyendo con bloques Ingenio Blocks" />
          <StickerBadge />
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
  return (
    <section className="lp-como" id="como-funciona">
      <span className="lp-chip lp-chip-lila">la experiencia</span>
      <h2 className="lp-h2">cómo funciona</h2>
      <span className="lp-underline" />
      <div className="lp-pasos">
        {PASOS.map((paso, i) => (
          <div className="lp-paso" key={paso.num}>
            <div className="lp-paso-foto" style={{ '--tilt-color': paso.color }}>
              <img src={paso.foto} alt={paso.titulo} />
            </div>
            <div className="lp-paso-body">
              <span className="lp-paso-num">{paso.num}</span>
              <span className="lp-paso-dot" style={{ background: paso.color }} />
              <h3>{paso.titulo}</h3>
              <p>{paso.texto}</p>
            </div>
            {i < 2 && <span className="lp-paso-arrow"><ChevronsRight /></span>}
          </div>
        ))}
      </div>
      <a href="#beneficios" className="lp-btn-yellow lp-btn-play">
        ¿cómo empezar a construir? <IconPlayCircle />
      </a>
    </section>
  )
}

function Beneficios() {
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
          {VIDEOS.map(v => (
            <article className="lp-video-card" key={v.titulo}>
              <div className="lp-video-thumb">
                <img src={v.foto} alt={v.titulo} />
                <span className="lp-video-play"><IconPlaySolid /></span>
              </div>
              <div className="lp-video-body">
                <h4>{v.titulo}</h4>
                <p>{v.texto}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

function Kits() {
  const navigate = useNavigate()
  const [products, setProducts] = useState([])

  useEffect(() => {
    api.get('/catalog/products/')
      .then(res => setProducts(res.data))
      .catch(() => {}) // la landing funciona igual sin catálogo
  }, [])

  const findProduct = (...keywords) =>
    products.find(p => keywords.some(k => p.name.toLowerCase().includes(k)))

  const comprar = (product) => {
    if (product) navigate('/checkout', { state: { product } })
    else navigate('/tienda')
  }

  const kitInicial = findProduct('inicial', 'kit ingenio')
  const kit8 = findProduct('8 modelos', 'pack')
  const membresia = findProduct('membres')

  const precio = (product, fallback) =>
    product ? `$${parseInt(product.price).toLocaleString('es-CL')}` : fallback

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

      <div className="lp-cards">
        {/* Kit Inicial */}
        <article className="lp-card">
          <span className="lp-chip lp-chip-pago">pago único</span>
          <h3>Kit Inicial</h3>
          <p className="lp-card-desc"><strong>Kit de bloques Ingenio Blocks</strong> con más de 400 piezas + motor y batería, que permite construir más de 100 modelos.</p>
          <ul className="lp-checks">
            <li><IconCheck /> Acceso al aula virtual de Ingenio Blocks por 6 meses.</li>
            <li><IconCheck /> 24 modelos (1 cada semana).</li>
            <li><IconCheck /> Certificado de aprobación cada 12 modelos.</li>
            <li><IconCheck /> No incluye gastos de envío.</li>
          </ul>
          <div className="lp-price-box">
            <span className="lp-price">{precio(kitInicial, '$69.490')}</span>
            <span className="lp-price-note">/ pago único</span>
          </div>
          <button className="lp-btn-yellow lp-btn-card" onClick={() => comprar(kitInicial)}>comprar kit inicial</button>
        </article>

        {/* Kit 8 modelos */}
        <article className="lp-card">
          <span className="lp-chip lp-chip-pago">pago único</span>
          <h3>Kit 8 modelos</h3>
          <p className="lp-card-desc">Si ya eres parte del <strong>Mundo Ingenio Blocks</strong> puedes agregar más modelos a tu usuario. Los modelos irán en orden como hasta ahora y se liberará 1 a la semana.</p>
          <ul className="lp-checks">
            <li><IconCheck /> Acceso al aula virtual de Ingenio Blocks por 2 meses.</li>
            <li><IconCheck /> 8 modelos (1 cada semana).</li>
            <li><IconCheck /> Certificado de aprobación cada 12 modelos.</li>
            <li><IconCheck /> Máximo de compra 3 packs.</li>
          </ul>
          <div className="lp-price-box">
            <span className="lp-price">{precio(kit8, '$12.900')}</span>
            <span className="lp-price-note">/ pago único</span>
          </div>
          <button className="lp-btn-yellow lp-btn-card" onClick={() => comprar(kit8)}>comprar kit 8 modelos</button>
        </article>

        {/* Membresía Familiar */}
        <article className="lp-card lp-card-purple">
          <span className="lp-ribbon">Próximamente</span>
          <span className="lp-chip lp-chip-mensual">pago mensual</span>
          <h3>Membresía Familiar</h3>
          <p className="lp-card-desc"><strong>Kit de bloques Ingenio Blocks</strong> con más de 400 piezas + motor y batería, que permite construir más de 100 modelos.</p>
          <ul className="lp-checks lp-checks-yellow">
            <li><IconCheck color="#ffcb00" /> Pertenecer al Club Ingenio Blocks.</li>
            <li><IconCheck color="#ffcb00" /> Contenido informativo exclusivo para miembros.</li>
            <li><IconCheck color="#ffcb00" /> Participar en las competencias.</li>
            <li><IconCheck color="#ffcb00" /> Premios al ganador.</li>
          </ul>
          <div className="lp-price-box">
            <span className="lp-price">{precio(membresia, '$9.990')}</span>
            <span className="lp-price-note">/ pago mensual</span>
          </div>
          <button className="lp-btn-yellow lp-btn-card" onClick={() => comprar(membresia)}>comprar membresía</button>
        </article>
      </div>

      {/* Oferta */}
      <article className="lp-oferta">
        <span className="lp-ribbon lp-ribbon-red">Oferta</span>
        <div className="lp-oferta-head">
          <h3>Oferta</h3>
          <span className="lp-chip lp-chip-pago">pago único</span>
          <p className="lp-card-desc"><strong>Kit de bloques Ingenio Blocks</strong> con más de 400 piezas + motor y batería, que permite construir más de 100 modelos.</p>
        </div>
        <ul className="lp-checks lp-oferta-checks">
          <li><IconCheck /> Acceso al aula virtual de Ingenio Blocks por 6 meses.</li>
          <li><IconCheck /> 24 modelos (1 cada semana).</li>
          <li><IconCheck /> Certificado de aprobación cada 12 modelos.</li>
          <li><IconCheck /> No incluye gastos de envío.</li>
        </ul>
        <div className="lp-oferta-buy">
          <div className="lp-price-box lp-oferta-price">
            <span className="lp-price lp-price-red">$59.490</span>
            <span className="lp-price-antes">antes <s>$69.490</s></span>
          </div>
          <button className="lp-btn-yellow lp-btn-card" onClick={() => comprar(kitInicial)}>comprar kit inicial</button>
        </div>
      </article>
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
  return (
    <section className="lp-testimonios">
      <span className="lp-chip lp-chip-lila">comunidad feliz</span>
      <h2 className="lp-h2">testimonios</h2>
      <span className="lp-underline" />
      <div className="lp-testimonios-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <article className="lp-testimonio" key={i}>
            <div className="lp-stars">
              {Array.from({ length: 5 }).map((_, j) => <IconStar key={j} />)}
            </div>
            <span className="lp-quote" aria-hidden="true">“</span>
            <p>
              "Queríamos una actividad educativa y con diversión garantizada. Con este
              plan mensual encontramos la mezcla ideal de teoría y armado práctico."
            </p>
            <footer>
              <strong>Mario Gomez</strong>
              <span>Santiago, Chile</span>
            </footer>
          </article>
        ))}
      </div>
    </section>
  )
}

function Concurso() {
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
          <p>
            Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
            tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam,
            quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo
            consequat.
          </p>
        </div>
      </div>
    </section>
  )
}

function Faq() {
  const [open, setOpen] = useState(0)
  const [verMas, setVerMas] = useState(false)
  const visibles = verMas ? FAQS : FAQS.slice(0, 6)

  return (
    <section className="lp-faq">
      <span className="lp-chip lp-chip-lila">resuelve tus dudas</span>
      <h2 className="lp-h2">Preguntas Frecuentes</h2>
      <span className="lp-underline" />
      <div className="lp-faq-list">
        {visibles.map((f, i) => (
          <div className={`lp-faq-item${open === i ? ' open' : ''}`} key={f.q}>
            <button className="lp-faq-q" onClick={() => setOpen(open === i ? -1 : i)}>
              {f.q}
              <span className={`lp-faq-toggle${open === i ? ' minus' : ''}`}>
                {open === i ? '−' : '+'}
              </span>
            </button>
            {open === i && <div className="lp-faq-a">{f.a}</div>}
          </div>
        ))}
      </div>
      {!verMas && FAQS.length > 6 && (
        <button className="lp-vermas" onClick={() => setVerMas(true)}>ver más</button>
      )}
    </section>
  )
}

function Contacto() {
  const [form, setForm] = useState({ nombre: '', apellido: '', email: '', telefono: '', comentarios: '' })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const enviar = (e) => {
    e.preventDefault()
    const body = `Nombre: ${form.nombre} ${form.apellido}%0AEmail: ${form.email}%0ATeléfono: ${form.telefono}%0A%0A${encodeURIComponent(form.comentarios)}`
    window.location.href = `mailto:contacto@ingenioblocks.com?subject=Contacto desde la web&body=${body}`
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
          <button type="submit" className="lp-btn-yellow">contáctanos</button>
        </form>
      </div>
    </section>
  )
}

function LandingFooter() {
  return (
    <footer className="lp-footer">
      <img src={logo} alt="Ingenio Blocks" className="lp-footer-logo" />
      <div className="lp-footer-center">
        <nav>
          <a href="#como-funciona">Cómo funciona</a>
          <a href="#beneficios">Beneficios</a>
          <a href="#kits">Kits</a>
          <a href="#quienes-somos">Quiénes somos</a>
          <a href="#contacto">Contacto</a>
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

export default function Landing() {
  const [activeSection, setActiveSection] = useState('')

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
    <div className="lp">
      <Hero activeSection={activeSection} />
      <ComoFunciona />
      <Beneficios />
      <Kits />
      <QuienesSomos />
      <Testimonios />
      <Concurso />
      <Faq />
      <Contacto />
      <LandingFooter />
    </div>
  )
}
