import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Link, Navigate } from 'react-router-dom'
import { LandingFooter, LandingHeader, usePaginaModelos } from '../components/LandingSections'
import { ocultarPreloader } from '../preloader'
import './landing.css'
import './modelos.css'

/*
  La vitrina: todos los modelos que se pueden armar, con su trailer.

  Repite en parte lo que ya muestran los trailers de "Beneficios" en la portada,
  y eso fue una decisión del cliente. La diferencia real es que acá está el
  catálogo COMPLETO y en la portada solo tres, así que sirve como la página que
  se manda por WhatsApp cuando alguien pregunta "¿y qué se puede hacer?".

  Se puede apagar entera desde el panel (Portada → Modelos): con `visible` en
  falso desaparece del menú y esta ruta manda a la portada.
*/

function TrailerModal({ modelo, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const overflowPrevio = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflowPrevio
    }
  }, [onClose])

  return createPortal(
    <div className="lp-vmodal" onClick={onClose}>
      <div className="lp-vmodal-inner" onClick={(e) => e.stopPropagation()}>
        <button className="lp-vmodal-close" onClick={onClose} aria-label="Cerrar trailer">×</button>
        <div className="lp-vmodal-frame">
          <iframe
            src={`https://www.youtube.com/embed/${modelo.youtube_id}?autoplay=1&rel=0`}
            title={modelo.nombre}
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

const IconPlay = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M8 5v14l11-7z" />
  </svg>
)

function Tarjeta({ modelo, onVerTrailer }) {
  const tieneTrailer = Boolean(modelo.youtube_id)

  // Sin trailer la tarjeta no es un botón: un cursor de mano sobre algo que no
  // hace nada al apretarlo se siente como que la página está rota.
  const Contenedor = tieneTrailer ? 'button' : 'div'
  const props = tieneTrailer
    ? { type: 'button', onClick: () => onVerTrailer(modelo),
        'aria-label': `Ver el trailer de ${modelo.nombre}` }
    : {}

  return (
    <Contenedor className={'mdl-card' + (tieneTrailer ? ' con-trailer' : '')} {...props}>
      <div className="mdl-foto">
        {modelo.foto_url
          ? <img src={modelo.foto_url} alt={modelo.nombre} loading="lazy" />
          : <span className="mdl-sin-foto" aria-hidden="true">🧱</span>}
        {tieneTrailer && <span className="mdl-play"><IconPlay /></span>}
      </div>
      <div className="mdl-texto">
        <h3>{modelo.nombre}</h3>
        {modelo.descripcion && <p>{modelo.descripcion}</p>}
      </div>
    </Contenedor>
  )
}

export default function Modelos() {
  const datos = usePaginaModelos()
  const [trailer, setTrailer] = useState(null)

  useEffect(() => { if (datos) ocultarPreloader() }, [datos])

  if (!datos) return null                       // el preloader sigue a la vista
  // Apagada desde el panel: no se deja una página huérfana accesible por URL.
  if (!datos.visible) return <Navigate to="/" replace />

  const modelos = datos.modelos || []

  return (
    <div className="lp">
      {/* El encabezado va DENTRO de la franja morada, igual que en la portada:
          sus enlaces son blancos por diseño (.lp-nav a en landing.css) y sobre
          fondo claro desaparecían. */}
      <section className="mdl-hero">
        <LandingHeader active="modelos" />
        <div className="mdl-hero-inner">
          <h1>{datos.titulo}</h1>
          {datos.intro && <p>{datos.intro}</p>}
        </div>
      </section>

      <main className="mdl-body">
        {modelos.length === 0 ? (
          <div className="mdl-vacio">
            <span aria-hidden="true">🧱</span>
            <h2>Estamos preparando esta página</h2>
            <p>Muy pronto vas a poder ver acá todos los modelos que se arman.</p>
            <Link to="/#kits" className="lp-btn-yellow">Ver los kits</Link>
          </div>
        ) : (
          <>
            <p className="mdl-conteo">
              {modelos.length} modelo{modelos.length === 1 ? '' : 's'} para armar
            </p>
            <div className="mdl-grid">
              {modelos.map(m => (
                <Tarjeta key={m.id} modelo={m} onVerTrailer={setTrailer} />
              ))}
            </div>

            <div className="mdl-cierre">
              <h2>¿Te gustaron?</h2>
              <p>Todos se arman con el mismo kit, y cada semana se abre uno nuevo.</p>
              <Link to="/#kits" className="lp-btn-yellow">quiero mi kit</Link>
            </div>
          </>
        )}
      </main>

      <LandingFooter />

      {trailer && <TrailerModal modelo={trailer} onClose={() => setTrailer(null)} />}
    </div>
  )
}
