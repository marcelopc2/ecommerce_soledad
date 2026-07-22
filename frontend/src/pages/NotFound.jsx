import { Link } from 'react-router-dom'
import './notfound.css'

/**
 * 404 del lado del frontend.
 *
 * Las plantillas 404.html de Django NO cubren esto: en producción nginx sirve
 * el index.html de React para cualquier ruta desconocida (fallback de SPA), así
 * que Django nunca se entera. Sin esta ruta comodín, /cualquier-cosa mostraría
 * la app en blanco.
 */
export default function NotFound() {
  return (
    <div className="nf">
      <span className="nf-deco nf-d1" aria-hidden="true" />
      <span className="nf-deco nf-d2" aria-hidden="true" />
      <span className="nf-deco nf-d3" aria-hidden="true" />
      <span className="nf-deco nf-d4" aria-hidden="true" />

      <main className="nf-card">
        <p className="nf-code">404</p>
        <h1>Esta pieza no encaja</h1>
        <span className="nf-underline" />
        <p className="nf-msg">
          La página que buscas no existe o cambió de lugar. Puede que el enlace
          esté antiguo o que haya un error de tipeo en la dirección.
        </p>
        <div className="nf-acciones">
          <Link to="/" className="nf-btn nf-btn-amarillo">Volver al inicio</Link>
          <Link to="/#kits" className="nf-btn nf-btn-borde">Ver los kits</Link>
        </div>
        <p className="nf-marca">Ingenio Blocks</p>
      </main>
    </div>
  )
}
