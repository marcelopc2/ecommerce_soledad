import { useState, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ocultarPreloader } from '../preloader'
import {
  Contacto, LandingFooter, LandingHeader, PlusDeco, Sparkle, useScrollReveal,
  IconInstagram, IconFacebook, IconYoutube,
} from '../components/LandingSections'
import './landing.css'

import logo from '../assets/landing/logo-ingenioblocks.svg'
import heroNino from '../assets/landing/hero-nino.webp'
import logoWebpay from '../assets/pagos/webpay.png'
import logoMercadoPago from '../assets/pagos/mercadopago.png'
import logoVisa from '../assets/pagos/visa.png'
import logoMastercard from '../assets/pagos/mastercard.png'
import logoRedcompra from '../assets/pagos/redcompra.png'
import quienesSomosNino from '../assets/landing/quienes-somos-nino.png'
import club3d from '../assets/landing/club-3d.png'
import ganadorFoto from '../assets/landing/ganador-foto.svg'

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

const IconPlayCircle = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" />
  </svg>
)

const IconGrilla = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </svg>
)

/* Chevron de trazo y no el carácter "‹": el glifo depende de la fuente, se ve
   finito y no queda centrado igual en todos los navegadores. */
const IconChevron = ({ derecha = false }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2.5"
       strokeLinecap="round" strokeLinejoin="round"
       style={derecha ? { transform: 'rotate(180deg)' } : undefined}>
    <polyline points="15 18 9 12 15 6" />
  </svg>
)

const IconPlaySolid = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="#2f0053"><polygon points="8 5 19 12 8 19 8 5" /></svg>
)

/* Convención que la clienta escribe a mano en el panel: una línea que empieza
   con +/-/* cambia el ícono y el color de su viñeta. El símbolo se saca del
   texto mostrado, no forma parte del beneficio.

   No basta con cambiar el color: quien no distingue verde de rojo vería tres
   vistos buenos idénticos y leería "incluido" en los tres casos. Por eso cada
   tono trae además una forma distinta.

     +  incluido        visto verde
     -  no incluido     guión rojo
     *  ojo con esto    exclamación ámbar */
const TIPO_POR_SIMBOLO = { '+': 'si', '-': 'no', '*': 'aviso' }
const TONO_BENEFICIO = { si: '#00a63e', no: '#e7000b', aviso: '#e8a600' }

const IconBeneficio = ({ tipo = 'si', color }) => {
  const tono = color || TONO_BENEFICIO[tipo]
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="11" fill={tono} opacity="0.15" />
      {tipo === 'si' && (
        <path d="M7 12.5l3.2 3.2L17 9" stroke={tono} strokeWidth="2.4"
              strokeLinecap="round" strokeLinejoin="round" />
      )}
      {tipo === 'no' && (
        <path d="M7.6 12h8.8" stroke={tono} strokeWidth="2.4" strokeLinecap="round" />
      )}
      {tipo === 'aviso' && (
        <>
          <path d="M12 6.8v6.4" stroke={tono} strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="12" cy="16.9" r="1.3" fill={tono} />
        </>
      )}
    </svg>
  )
}

function parseFeatureLine(raw) {
  const m = raw.match(/^([+\-*])\s*(.*)$/)
  // `marcada` distingue "sin símbolo" de "+": ambas son un visto verde, pero
  // solo la que no trae símbolo cede su color al amarillo de la tarjeta morada.
  if (!m) return { text: raw, tipo: 'si', marcada: false }
  return { text: m[2], tipo: TIPO_POR_SIMBOLO[m[1]], marcada: true }
}

const IconStar = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="#ffba00">
    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
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


// Galería de TODOS los modelos, en un modal. Antes esto era un carrusel dentro
// del recuadro: mostraba 3 de 44 y había que empujarlo de a poco, así que no
// cumplía lo que la sección promete -mostrar todo lo que se puede armar-.
//
// Se monta en document.body (portal) para que ningún transform ni contexto de
// apilamiento de la portada lo afecte.
function GaleriaModelos({ modelos, inicial = null, onCerrar }) {
  // El trailer se ve DENTRO de esta misma ventana, reemplazando la grilla, en
  // vez de abrir un segundo modal encima: dos capas de modal se vuelven un
  // laberinto para cerrar, sobre todo en el celular.
  const [viendo, setViendo] = useState(inicial)

  useEffect(() => {
    const alTeclear = (e) => {
      if (e.key !== 'Escape') return
      // Escape retrocede de a un paso: primero cierra el video, después la
      // galería. Cerrar todo de una borraría el lugar donde iba mirando.
      if (viendo) setViendo(null)
      else onCerrar()
    }
    document.addEventListener('keydown', alTeclear)
    const overflowPrevio = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', alTeclear)
      document.body.style.overflow = overflowPrevio
    }
  }, [viendo, onCerrar])

  const separador = viendo?.trailer?.includes('?') ? '&' : '?'

  return createPortal(
    <div className="lp-gmodal" onClick={onCerrar}>
      <div className="lp-gmodal-inner" onClick={(e) => e.stopPropagation()}>
        <header className="lp-gmodal-head">
          {viendo ? (
            <button type="button" className="lp-gmodal-volver" onClick={() => setViendo(null)}>
              <IconChevron /> Volver a los modelos
            </button>
          ) : (
            <h3>Todos nuestros modelos <span>({modelos.length})</span></h3>
          )}
          <button type="button" className="lp-gmodal-close" onClick={onCerrar}
                  aria-label="Cerrar">×</button>
        </header>

        {viendo ? (
          <div className="lp-gmodal-player">
            <div className="lp-vmodal-frame">
              <iframe
                src={`${viendo.trailer}${separador}autoplay=1&rel=0`}
                title={viendo.titulo}
                allow="autoplay; encrypted-media; fullscreen"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
            </div>
            <p className="lp-gmodal-titulo">{viendo.titulo}</p>
          </div>
        ) : (
          <div className="lp-gmodal-grid">
            {modelos.map((m) => {
              // Con trailer es un botón (se puede ver el video); sin trailer es
              // una figura: un botón que no hace nada al pulsarlo promete algo
              // que no existe.
              const Tarjeta = m.trailer ? 'button' : 'figure'
              return (
                <Tarjeta
                  key={m.id}
                  className="lp-gmodal-card"
                  {...(m.trailer ? {
                    type: 'button',
                    onClick: () => setViendo(m),
                    'aria-label': `Ver el video de ${m.titulo}`,
                  } : {})}
                >
                  <div className="lp-gmodal-thumb">
                    <img src={m.imagen} alt={m.titulo} loading="lazy" />
                    {m.trailer && <span className="lp-video-play"><IconPlaySolid /></span>}
                  </div>
                  <span className="lp-gmodal-nombre">{m.titulo}</span>
                </Tarjeta>
              )
            })}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

function Beneficios() {
  const [modelos, setModelos] = useState([])
  const [galeria, setGaleria] = useState(false)

  useEffect(() => {
    api.get('/catalog/vitrina/')
      .then(res => setModelos(res.data))
      .catch(() => {}) // la portada funciona igual sin la vitrina
  }, [])

  // Barajados en el navegador y no en el servidor: cualquier caché intermedia
  // congelaría un orden y dejarían de salir distintos en cada recarga, que es
  // justamente lo que se busca. useMemo para que no se rebarajen solos en cada
  // re-render (si no, al abrir un trailer se reordenaban por detrás).
  const barajados = useMemo(() => {
    const copia = [...modelos]
    for (let i = copia.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[copia[i], copia[j]] = [copia[j], copia[i]]
    }
    return copia
  }, [modelos])

  // Inclinación aleatoria por tarjeta, para que las tres no se vean como un
  // catálogo de stock. useMemo la deja estable entre re-renders: si no, la
  // tarjeta cambiaba de ángulo en cada hover.
  const rotations = useMemo(
    () => barajados.slice(0, 3).map(() => (Math.random() * 6 - 3).toFixed(2)),
    [barajados],
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
          {/* Entre "propio" y "ritmo" hay un ESPACIO DURO (U+00A0, invisible en el editor): amarra
                las dos palabras para que el navegador nunca las separe y "ritmo."
                no quede sola en la ultima linea. Se probo antes apretando el
                interletrado (-5%), pero eso corre TODOS los cortes de linea a la vez:
                dejaba de quedar sola a 1536px y pasaba a quedar sola a 1600px. El
                ancho de pantalla es variable, asi que unir las palabras es lo estable. */}
          <p>
            Nuestra Plataforma está diseñada en un formato amigable que permite a{' '}
            <strong>niños y niñas desde los 6 años</strong>, sumergirse fácilmente en
            emocionantes talleres desarrollados con metodologías de aprendizaje en
            espiral. Esto significa que podrán avanzar a su propio{' '}ritmo.
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
        {/* Tres de muestra -sorteados en cada recarga- y el botón para verlos
            todos. Solo el botón dejaba el recuadro vacío: la sección promete
            enseñar los modelos, no anunciar que existen. */}
        <div className="lp-videos">
          {barajados.slice(0, 3).map((m, i) => {
            const Tarjeta = m.trailer ? 'button' : 'article'
            return (
              <Tarjeta
                className="lp-video-card"
                key={m.id}
                style={{ '--hover-rot': `${rotations[i] || 0}deg` }}
                {...(m.trailer ? {
                  type: 'button',
                  // Abre la MISMA galería, ya mostrando ese video: desde ahí
                  // "Volver a los modelos" lleva al listado completo, en vez de
                  // dejar al visitante en un callejón sin salida.
                  onClick: () => setGaleria(m),
                  'aria-label': `Ver el video de ${m.titulo}`,
                } : {})}
              >
                <div className="lp-video-thumb">
                  <img src={m.imagen} alt={m.titulo} loading="lazy" />
                  {m.trailer && <span className="lp-video-play"><IconPlaySolid /></span>}
                </div>
                <div className="lp-video-body">
                  <h4>{m.titulo}</h4>
                </div>
              </Tarjeta>
            )
          })}
        </div>

        {modelos.length > 0 && (
          <button
            type="button"
            className="lp-ver-modelos"
            onClick={() => setGaleria(true)}
          >
            <IconGrilla />
            Ver todos los modelos
          </button>
        )}
      </div>
      {galeria && (
        <GaleriaModelos
          modelos={barajados}
          inicial={galeria === true ? null : galeria}
          onCerrar={() => setGaleria(false)}
        />
      )}
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
        {product.features_list.map((raw, i) => {
          const { text, tipo, marcada } = parseFeatureLine(raw)
          return (
            <li key={i}>
              <IconBeneficio tipo={tipo} color={!marcada && purple ? '#ffcb00' : undefined} /> {text}
            </li>
          )
        })}
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
        {product.features_list.map((raw, i) => {
          const { text, tipo } = parseFeatureLine(raw)
          return <li key={i}><IconBeneficio tipo={tipo} /> {text}</li>
        })}
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

/* Franja "Pagos 100% seguros".

   Antes era un SVG exportado del Figma (pagos-badges.svg, 171 kB). Pasarlo a
   HTML+CSS pesa una fracción de eso, deja el texto seleccionable y legible por
   lectores de pantalla, y permite agregar o sacar un medio de pago sin volver a
   exportar nada desde el diseño. */
/* `alto` es una excepción, no la norma: casi todos usan el alto que fija el CSS.
   El de Mercado Pago trae margen blanco dentro del propio archivo y su texto va
   en DOS líneas, así que a la altura común cada línea queda en unos 7px y se ve
   mucho más chico que el resto. */
const MEDIOS_DE_PAGO = [
  { nombre: 'Webpay Plus', logo: logoWebpay },
  { nombre: 'Mercado Pago', logo: logoMercadoPago, alto: 32 },
  { nombre: 'Visa', logo: logoVisa },
  { nombre: 'Mastercard', logo: logoMastercard },
  { nombre: 'Redcompra', logo: logoRedcompra },
]

const IconEscudo = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 2.5 4.5 5.6v5.5c0 4.6 3.2 8.9 7.5 10.4 4.3-1.5 7.5-5.8 7.5-10.4V5.6L12 2.5z"
          fill="var(--lp-yellow)" />
    <path d="m8.6 12.1 2.3 2.3 4.5-4.6" stroke="#2f0053" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

function PagosSeguros() {
  return (
    <div className="lp-pagos">
      <p className="lp-pagos-titulo">
        <IconEscudo />
        pagos 100% seguros
      </p>
      <ul className="lp-pagos-logos">
        {MEDIOS_DE_PAGO.map(medio => (
          <li key={medio.nombre}>
            {/* El alt lleva el nombre porque cada logo es la única señal de que
                ese medio de pago está disponible: sin él la franja no dice nada
                a quien usa lector de pantalla. */}
            {/* Se pasa como variable CSS y no como height directo para que la
                regla de celular pueda seguir escalándolo (ver landing.css). */}
            <img
              src={medio.logo}
              alt={medio.nombre}
              loading="lazy"
              style={medio.alto ? { '--alto-logo': `${medio.alto}px` } : undefined}
            />
          </li>
        ))}
      </ul>
    </div>
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
      <h2 className="lp-h2 lp-h2-white">nuestros productos</h2>
      <span className="lp-underline" />
      <p className="lp-kits-intro">
        Te invitamos a hacerte parte del Mundo Ingenio Blocks y comenzar a disfrutar de
        esta divertida forma de aprender a través de nuestros talleres virtuales, con más
        de 100 modelos motorizados. ¡Explora y crea un modelo diferente cada semana!
      </p>
      <PagosSeguros />

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

/* Zona lateral del carrusel. Va FUERA de Testimonios a propósito: definida
   dentro, React la trata como un tipo de componente distinto en cada render y
   desmonta el botón, que es la forma más fácil de perder un hover en curso. */
function CostadoTestimonios({ dir, etiqueta, onEntrar, onSalir, onClic }) {
  return (
    <button
      type="button"
      className={`lp-testi-costado ${dir < 0 ? 'izq' : 'der'}`}
      aria-label={etiqueta}
      onMouseEnter={() => onEntrar(dir)}
      onMouseLeave={onSalir}
      onFocus={() => onEntrar(dir)}
      onBlur={onSalir}
      onClick={() => onClic(dir)}
    >
      <span aria-hidden="true">{dir < 0 ? '‹' : '›'}</span>
    </button>
  )
}

function Testimonios() {
  const [testimonials, setTestimonials] = useState([])
  const [desborda, setDesborda] = useState(false)
  const [abierto, setAbierto] = useState(null)   // testimonio mostrado en el modal, o null
  const [sobre, setSobre] = useState(null)       // { t, rect } de la tarjeta bajo el puntero
  const pistaRef = useRef(null)
  const dirRef = useRef(0)
  const rafRef = useRef(0)

  useEffect(() => {
    api.get('/catalog/testimonials/')
      .then(res => setTestimonials(res.data))
      .catch(() => {}) // la landing funciona igual sin testimonios
  }, [])

  // Las zonas laterales solo aparecen si de verdad hay algo fuera de vista: con
  // 3 testimonios caben todos y unas flechas que no llevan a ninguna parte solo
  // confunden. Se recalcula al cambiar el ancho porque en móvil caben menos.
  useEffect(() => {
    const el = pistaRef.current
    if (!el) return
    const medir = () => setDesborda(el.scrollWidth > el.clientWidth + 4)
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [testimonials])

  // Desplazamiento continuo mientras el puntero está sobre un costado.
  const paso = () => {
    const el = pistaRef.current
    if (el && dirRef.current) el.scrollLeft += dirRef.current * 7
    rafRef.current = requestAnimationFrame(paso)
  }
  const arrancar = (dir) => {
    // Quien pidió menos animación no espera que la página se mueva sola bajo el
    // cursor; ahí el costado sigue sirviendo, pero solo con clic.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    dirRef.current = dir
    if (!rafRef.current) rafRef.current = requestAnimationFrame(paso)
  }
  const frenar = () => {
    dirRef.current = 0
    cancelAnimationFrame(rafRef.current)
    rafRef.current = 0
  }
  // Al hacer clic salta una "página" completa, que es lo que espera quien no
  // descubre el desplazamiento por hover (y lo que hace el teclado con Enter).
  const saltar = (dir) => {
    const el = pistaRef.current
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: 'smooth' })
  }
  // Detener siempre al desmontar: si no, el requestAnimationFrame sigue vivo.
  useEffect(() => () => cancelAnimationFrame(rafRef.current), [])

  // El panel del hover va con posición fija sobre la tarjeta: si algo se
  // desplaza (la página o la propia pista) la tarjeta se mueve y el panel se
  // quedaría flotando en el aire, así que se cierra. `true` = fase de captura,
  // porque el evento scroll no burbujea y el de la pista no llegaría a window.
  useEffect(() => {
    if (!sobre) return
    const cerrar = () => setSobre(null)
    window.addEventListener('scroll', cerrar, true)
    window.addEventListener('resize', cerrar)
    return () => {
      window.removeEventListener('scroll', cerrar, true)
      window.removeEventListener('resize', cerrar)
    }
  }, [sobre])

  return (
    <section className="lp-testimonios">
      <span className="lp-chip lp-chip-lila">comunidad feliz</span>
      <h2 className="lp-h2">testimonios</h2>
      <span className="lp-underline" />

      <div className={'lp-testi-carrusel' + (desborda ? ' con-costados' : '')}>
        {desborda && (
          <CostadoTestimonios dir={-1} etiqueta="Ver testimonios anteriores"
                              onEntrar={arrancar} onSalir={frenar} onClic={saltar} />
        )}

        {/* Con 3 o menos, las tarjetas se reparten todo el ancho de la grilla
            (como cualquier otra sección); recién con 4 pasan al ancho de "4 por
            pantalla" y lo que sobra se desplaza al costado. */}
        <div
          className={'lp-testi-pista' + (testimonials.length <= 3 ? ' pocos' : '')}
          ref={pistaRef}
        >
          {testimonials.map((t) => (
            <article className="lp-testimonio" key={t.id}>
              {/* Al pasar el mouse se despliega el texto completo (ver
                  TestimonioHover). El clic abre el modal, que es la vía para
                  quien no tiene puntero: teléfonos y teclado. */}
              <div
                /* Mientras el panel del hover está encima, la tarjeta se
                   esconde (sigue ocupando su lugar): así no puede asomar por
                   detrás durante la animación de escala. */
                className={'lp-testimonio-in' + (sobre?.t.id === t.id ? ' tapada' : '')}
                role="button"
                tabIndex={0}
                aria-haspopup="dialog"
                aria-label={`Leer el testimonio completo de ${t.name}`}
                /* Al abrir el modal se retira el panel del hover: queda debajo
                   del modal, que le tapa el mouse, así que nunca recibiría su
                   mouseleave y se quedaría abierto al cerrar el modal. */
                onClick={() => { setSobre(null); setAbierto(t) }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault(); setSobre(null); setAbierto(t)
                  }
                }}
                onMouseEnter={(e) => {
                  // Solo con puntero de verdad: en una pantalla táctil el toque
                  // también dispara mouseenter y se abrirían panel y modal a la vez.
                  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
                  setSobre({ t, rect: e.currentTarget.getBoundingClientRect() })
                }}
              >
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

        {desborda && (
          <CostadoTestimonios dir={1} etiqueta="Ver más testimonios"
                              onEntrar={arrancar} onSalir={frenar} onClic={saltar} />
        )}
      </div>

      {sobre && (
        <TestimonioHover
          testimonio={sobre.t}
          rect={sobre.rect}
          onSalir={() => setSobre(s => (s && s.t.id === sobre.t.id ? null : s))}
        />
      )}
      {abierto && <TestimonioModal testimonio={abierto} onClose={() => setAbierto(null)} />}
    </section>
  )
}

/* Texto completo al pasar el mouse.

   La clave para que no parpadee es que el panel aparece ENCIMA de la tarjeta,
   cubriéndola por completo, y solo crece hacia abajo. El intento anterior
   mandaba la tarjeta al centro de la pantalla con :hover y era inestable: al
   irse la tarjeta, el cursor dejaba de estar sobre ella, el navegador cancelaba
   el :hover, la tarjeta volvía… y vuelta a empezar. Acá el cursor queda siempre
   dentro del panel, así que el estado no puede oscilar. Se cierra con el
   mouseleave del propio panel, no con el de la tarjeta.

   Va en un portal porque la pista de testimonios tiene overflow y recortaría
   cualquier cosa más alta que ella. */
const MARGEN_HOVER = 16

/* Ancho del panel: algo más que la tarjeta. Con el ancho justo de la tarjeta un
   testimonio largo se convertía en una columna de 600px de alto y 220 de ancho,
   incómoda de leer; ensanchándolo baja a un bloque proporcionado. Se desplaza a
   la izquierda la mitad de lo que crece, para quedar centrado sobre la tarjeta,
   y se limita al viewport sin dejar de taparla nunca.

   El tope de 400 asume la tarjeta angosta de "4 por pantalla" (~246px): crece
   1.5x y queda bajo el tope sin problema. Con 3 o menos testimonios la tarjeta
   se estira a todo el ancho de la grilla (.pocos, ver landing.css) y puede
   medir bastante más que esos 400 -con 2 testimonios, unos 500px-. Sin el
   Math.max de abajo el tope ganaba igual y el panel salía MÁS ANGOSTO que la
   tarjeta que se supone que cubre: el hover se veía como si la tarjeta se
   hubiera encogido, en vez de crecer. El panel nunca debe ser más chico que
   la tarjeta; si ya es más ancha que el tope, se queda del mismo ancho. */
function medidasHover(rect) {
  const ancho = Math.max(rect.width, Math.min(rect.width * 1.5, 400))
  let left = rect.left - (ancho - rect.width) / 2
  left = Math.max(MARGEN_HOVER, Math.min(left, window.innerWidth - ancho - MARGEN_HOVER))
  left = Math.max(rect.right - ancho, Math.min(left, rect.left))
  return { ancho, left }
}

function TestimonioHover({ testimonio: t, rect, onSalir }) {
  const ref = useRef(null)
  const { ancho, left } = medidasHover(rect)
  const [top, setTop] = useState(rect.top)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const alto = el.offsetHeight
    let y = rect.top
    if (y + alto > window.innerHeight - MARGEN_HOVER) {
      // Sube lo justo para que quepa en pantalla, pero nunca tanto que deje de
      // tapar la tarjeta: si se despegara, el cursor quedaría fuera del panel.
      y = Math.max(window.innerHeight - MARGEN_HOVER - alto, rect.bottom - alto)
    }
    setTop(y)
  }, [rect])

  return createPortal(
    // aria-hidden: es una copia visual de la tarjeta para quien usa mouse. Los
    // lectores de pantalla ya tienen el texto por el modal (Enter en la tarjeta).
    // minHeight: con un testimonio corto el panel sería MÁS BAJO que la tarjeta
    // y ésta asomaría por debajo, como si hubiera dos tarjetas.
    <div
      ref={ref}
      className="lp-testi-hover"
      aria-hidden="true"
      style={{ left, top, width: ancho, minHeight: rect.height }}
      onMouseLeave={onSalir}
    >
      <div className="lp-stars">
        {Array.from({ length: t.rating }).map((_, j) => <IconStar key={j} />)}
      </div>
      <span className="lp-quote" aria-hidden="true">“</span>
      <p>"{t.quote}"</p>
      <footer>
        <strong>{t.name}</strong>
        <span>{t.location}</span>
      </footer>
    </div>,
    document.body,
  )
}

// Portal a document.body: así el modal no depende del overflow de ningún
// ancestro, ni de la pista horizontal de testimonios ni de nada más. Backdrop
// que cierra al clic, Escape, y scroll de fondo bloqueado mientras está abierto.
function TestimonioModal({ testimonio: t, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return createPortal(
    <div className="lp-testi-modal" onClick={onClose} role="dialog" aria-modal="true" aria-label={`Testimonio de ${t.name}`}>
      <div className="lp-testi-modal-inner" onClick={(e) => e.stopPropagation()}>
        <button className="lp-testi-modal-close" onClick={onClose} aria-label="Cerrar">×</button>
        <div className="lp-stars">
          {Array.from({ length: t.rating }).map((_, j) => <IconStar key={j} />)}
        </div>
        <p>"{t.quote}"</p>
        <footer>
          <strong>{t.name}</strong>
          <span>{t.location}</span>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

/* Sección "Club Ingenio Blocks" (reemplaza a la antigua de Concurso: los
   concursos ahora se explican acá dentro). El texto es el del diseño de la
   clienta, tal cual, salvo dos erratas evidentes del original: "pueden
   pertenecen" → "pueden pertenecer" y el paréntesis sin cerrar de las ruedas. */
const CLUB_BLOQUES = [
  {
    titulo: '¿Quiénes pueden pertenecer al Club Ingenio Blocks?',
    puntos: [
      'Todos aquellos que ya tengan nuestro Kit y una suscripción vigente.',
      'Si ya venció tu suscripción y quieres ser parte del club, sólo tienes que suscribirte a Ingenio Plus o comprar un pack de 8 modelos (2 meses – 1 modelo cada semana).',
    ],
  },
  {
    titulo: '¿Qué haremos en el Club?',
    puntos: [
      'Tendremos concursos periódicos en 2 categorías: de 6 a 8 años y de 9 a 12 años.',
      'Podrás hacer volar tu imaginación para crear modelos originales utilizando sólo las piezas del kit más motor y batería.',
      'Los ganadores se darán a conocer a través de nuestra página web además de premios personales.',
    ],
  },
  {
    titulo: '¿Qué premios tendremos?',
    puntos: [
      'Tu nombre y modelo serán publicados en nuestra página en la categoría en que participaste.',
      'Podrás convertir tu modelo en un nuevo curso de la plataforma.',
      'Un set de piezas para incluir a tu kit y construir nuevos modelos (1 motor, 1 batería + 4 ruedas grandes).',
      'Y muchas sorpresas más.',
    ],
  },
]

function Club() {
  return (
    <section className="lp-club-band" id="club">
      <div className="lp-club">
        <div className="lp-club-visual">
          <img src={club3d} alt="Logo de Ingenio Blocks construido con bloques" />
          <a className="lp-btn-yellow lp-btn-cta lp-club-cta" href="#kits">comprar ingenio plus</a>
        </div>
        <div className="lp-club-texto">
          <span className="lp-chip lp-chip-club">espacio virtual</span>
          <h2 className="lp-h2">club ingenio blocks</h2>
          <span className="lp-underline" />
          <p className="lp-club-intro">
            Queremos que Ingenio Blocks no sea sólo un set de bloques, sino que un espacio
            virtual donde los niños construyen, creen, se sientan siempre desafiados y
            desarrollen habilidades para la vida.
          </p>
          {CLUB_BLOQUES.map(bloque => (
            <div className="lp-club-bloque" key={bloque.titulo}>
              <h3>{bloque.titulo}</h3>
              <ul>
                {bloque.puntos.map(punto => <li key={punto}>{punto}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* Franja del concurso: va debajo del Club y tiene tres estados que se eligen
   desde el panel (Configuración → Concurso). Todo el contenido —textos, imagen
   y ganadores— sale de /catalog/concurso/, así que la clienta lo administra
   sola y no hay nada escrito acá que haya que ir a cambiar en el código. */
function Concurso({ datos }) {
  if (!datos || datos.estado === 'oculta') return null
  if (datos.estado === 'ganadores') return <Ganadores ganadores={datos.ganadores || []} />
  return <Convocatoria datos={datos} />
}

const IconRayo = () => (
  <svg className="lp-ganador-rayo" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M13.5 2 4 13.2h6.2L9.6 22 20 10.4h-6.6L13.5 2z" />
  </svg>
)

function Convocatoria({ datos }) {
  const { etiqueta, titulo, intro, bases = [], boton_texto, boton_enlace, sello, imagen_url } = datos
  return (
    <section className="lp-concurso-band">
      <div className="lp-convocatoria">
        <div className="lp-convocatoria-texto">
          {etiqueta && <span className="lp-chip lp-chip-lila">{etiqueta}</span>}
          <h2 className="lp-h2">{titulo}</h2>
          <span className="lp-underline" />
          {intro && <p className="lp-convocatoria-intro">{intro}</p>}
          {bases.length > 0 && (
            <ul className="lp-convocatoria-bases">
              {bases.map((base, i) => <li key={i}>{conEnlaces(base, `base-${i}`)}</li>)}
            </ul>
          )}
          <div className="lp-convocatoria-acciones">
            {boton_enlace && boton_texto && (
              <a className="lp-btn-concurso" href={boton_enlace}>{boton_texto}</a>
            )}
            <div className="lp-social lp-convocatoria-redes">
              <a href="https://instagram.com" target="_blank" rel="noreferrer" aria-label="Instagram"><IconInstagram /></a>
              <a href="https://facebook.com" target="_blank" rel="noreferrer" aria-label="Facebook"><IconFacebook /></a>
              <a href="https://youtube.com" target="_blank" rel="noreferrer" aria-label="YouTube"><IconYoutube /></a>
            </div>
          </div>
        </div>
        <div className="lp-convocatoria-visual">
          {imagen_url
            ? <img src={imagen_url} alt="Modelo participante del concurso" />
            : <img src={ganadorFoto} alt="" className="lp-convocatoria-pendiente" />}
          {sello && <span className="lp-convocatoria-sello">{sello}</span>}
        </div>
      </div>
    </section>
  )
}

function Ganadores({ ganadores }) {
  if (!ganadores.length) return null
  return (
    <section className="lp-ganadores-band">
      <div className="lp-ganadores">
        {ganadores.map(g => (
          <article className="lp-ganador" key={g.id}>
            <div className={`lp-ganador-poster ${g.tono}`}>
              <span className="lp-ganador-marca">Club Ingenio<br />Blocks</span>
              <IconRayo />
              <div className="lp-ganador-foto">
                <img src={g.foto_url || ganadorFoto} alt={g.foto_url ? `Proyecto de ${g.nombre}` : ''} />
              </div>
              <div className="lp-ganador-pie">
                <span>concurso</span>
                <span>{g.categoria}</span>
              </div>
            </div>
            <div className="lp-ganador-datos">
              <span className="lp-chip lp-chip-lila">concurso</span>
              <h3 className="lp-ganador-titulo">{g.titulo}</h3>
              <span className="lp-underline" />
              {g.anio && <p className="lp-ganador-anio">{g.anio}</p>}
              <p>{g.nombre}</p>
              {g.edad && <p>{g.edad}</p>}
              {g.texto && <p className="lp-ganador-texto">{g.texto}</p>}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

/* La respuesta llega como texto plano desde el panel, pero la clienta la escribe
   con estructura: párrafos y punteos. React no respeta los saltos de línea, así
   que sin esto todo salía corrido en un solo bloque.

   Se arma con elementos de React (nunca dangerouslySetInnerHTML): el texto lo
   edita la clienta desde el panel y meterlo como HTML sería una vía de XSS. */
const RE_ENLACE = /(https?:\/\/[^\s]+|[\w.+-]+@[\w-]+\.[\w.-]+)/g

function conEnlaces(texto, claveBase) {
  // split() con grupo de captura devuelve los enlaces como elementos propios,
  // así que basta mirar el comienzo. No se usa RE_ENLACE.test(): con la bandera
  // /g el regex guarda lastIndex entre llamadas y daría true/false alternado.
  return texto.split(RE_ENLACE).map((parte, i) => {
    if (parte.startsWith('http')) {
      return <a key={`${claveBase}-${i}`} href={parte} target="_blank" rel="noopener noreferrer">{parte}</a>
    }
    // Los correos también son clickeables: la clienta los escribe pelados en
    // las bases del concurso y en las preguntas frecuentes.
    if (parte.includes('@') && !parte.includes(' ')) {
      return <a key={`${claveBase}-${i}`} href={`mailto:${parte}`}>{parte}</a>
    }
    return parte
  })
}

function RespuestaFaq({ texto }) {
  if (!texto) return null

  // Se agrupan las líneas: las que empiezan con viñeta forman una lista, el
  // resto son párrafos.
  const bloques = []
  let lista = []
  const cerrarLista = () => {
    if (lista.length) { bloques.push({ tipo: 'lista', items: lista }); lista = [] }
  }

  for (const cruda of texto.split('\n')) {
    const linea = cruda.trim()
    if (!linea) { cerrarLista(); continue }
    const vinieta = linea.match(/^[•·*\-–—]\s+(.*)$/)
    if (vinieta) {
      lista.push(vinieta[1])
    } else {
      cerrarLista()
      bloques.push({ tipo: 'parrafo', texto: linea })
    }
  }
  cerrarLista()

  return (
    <>
      {bloques.map((b, i) => b.tipo === 'lista'
        ? <ul className="lp-faq-lista" key={i}>
            {b.items.map((it, j) => <li key={j}>{conEnlaces(it, `${i}-${j}`)}</li>)}
          </ul>
        : <p className="lp-faq-p" key={i}>{conEnlaces(b.texto, `${i}`)}</p>
      )}
    </>
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
              <div className="lp-faq-a"><RespuestaFaq texto={f.answer} /></div>
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


export default function Landing() {
  const [activeSection, setActiveSection] = useState('')
  const [products, setProducts] = useState([])
  const [concurso, setConcurso] = useState(null)
  const rootRef = useRef(null)
  const location = useLocation()
  // re-escanea el reveal cuando llegan los productos o el concurso (las dos
  // secciones aparecen después del primer render)
  useScrollReveal(rootRef, [products.length, concurso?.estado])

  useEffect(() => {
    const productos = api.get('/catalog/products/')
      .then(res => setProducts(res.data))
      .catch(() => {}) // la landing funciona igual sin catálogo
    const concursoReq = api.get('/catalog/concurso/')
      .then(res => setConcurso(res.data))
      .catch(() => {}) // sin respuesta, la franja del concurso no se muestra

    // La foto del hero es lo más pesado de la página y es lo primero que se ve:
    // si el overlay se destapa antes de que termine de bajar, queda un hueco en
    // blanco justo donde debería estar el niño, que es EXACTAMENTE el efecto de
    // "carga a la vista" que se quiere evitar.
    const foto = new Promise(resolve => {
      const img = new Image()
      img.onload = img.onerror = resolve
      img.src = heroNino
    })

    // document.fonts.ready evita el destello de texto sin estilo (se ve con la
    // tipografía del sistema un instante y salta a Quicksand/Outfit).
    const fuentes = document.fonts?.ready ?? Promise.resolve()

    // Tope de seguridad: si la API está caída o algo tarda de más, se muestra
    // la página igual en vez de dejar el overlay pegado para siempre.
    const tope = new Promise(resolve => setTimeout(resolve, 6000))

    let cancelado = false
    Promise.race([Promise.all([productos, concursoReq, foto, fuentes]), tope])
      .then(() => { if (!cancelado) ocultarPreloader() })
    return () => { cancelado = true }
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
      <Club />
      <Concurso datos={concurso} />
      <Faq />
      <Contacto />
      <LandingFooter />
    </div>
  )
}
