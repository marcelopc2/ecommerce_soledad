import { useEffect, useState } from 'react'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './aviso-preview.css'

/* Aviso de "sitio en construcción" para las direcciones de prueba.
 *
 * Mientras el sitio nuevo se revisa, vive en un subdominio y en la IP del
 * servidor. Quien llegue ahí por accidente -un link compartido, un buscador-
 * tiene que entender en dos segundos que no es la tienda de verdad y poder
 * irse a comprar al sitio que sí funciona.
 *
 * Se decide por el DOMINIO y no por una variable de compilación a propósito:
 * el día que ingenioblocks.com apunte a este servidor, el aviso desaparece
 * solo. Con una variable habría que acordarse de apagarla, y olvidarlo
 * significa recibir clientes reales con un cartel que dice "esto no está
 * listo". Que el criterio falle hacia el lado seguro importa más que la
 * elegancia. */

//: Los dominios donde el sitio es el de verdad y NO se muestra el aviso.
//: localhost va acá para no molestar mientras se programa.
const DEFINITIVOS = [
  'ingenioblocks.com',
  'www.ingenioblocks.com',
  'localhost',
  '127.0.0.1',
]

const CLAVE = 'aviso-preview-visto'

export function esSitioDePrueba() {
  if (typeof window === 'undefined') return false
  return !DEFINITIVOS.includes(window.location.hostname)
}

export default function AvisoPreview() {
  const [abierto, setAbierto] = useState(false)

  useEffect(() => {
    if (!esSitioDePrueba()) return
    let visto = false
    try {
      visto = sessionStorage.getItem(CLAVE) === '1'
    } catch {
      // Navegación privada o cookies bloqueadas: se muestra igual, que es el
      // lado seguro. Peor sería no avisarle a quien llegó por error.
    }
    if (!visto) setAbierto(true)
  }, [])

  const cerrar = () => {
    setAbierto(false)
    try {
      // En sessionStorage y no en localStorage: quien revisa el sitio no
      // quiere verlo en cada página, pero sí conviene que vuelva a aparecer en
      // la próxima visita, porque el aviso sigue siendo cierto.
      sessionStorage.setItem(CLAVE, '1')
    } catch { /* si no se puede guardar, se volverá a mostrar: no es grave */ }
  }

  if (!abierto) return null

  return (
    <div className="apv-fondo" role="dialog" aria-modal="true"
         aria-labelledby="apv-titulo" onClick={cerrar}>
      {/* stopPropagation: hacer clic DENTRO de la tarjeta no debe cerrarla;
          solo el clic en el fondo oscuro. */}
      <div className="apv-tarjeta" onClick={e => e.stopPropagation()}>
        <img src={logo} alt="Ingenio Blocks" className="apv-logo" />

        <span className="apv-chip">Sitio en construcción</span>

        <h2 id="apv-titulo">Esta versión todavía se está preparando</h2>

        <p>
          Estamos construyendo el nuevo sitio de Ingenio Blocks. Acá las compras
          y los datos son de prueba, así que <strong>no hagas pedidos por esta
          dirección</strong>.
        </p>

        <a className="apv-btn-principal" href="https://ingenioblocks.com">
          Ir al sitio oficial
        </a>

        <button type="button" className="apv-btn-seguir" onClick={cerrar}>
          Estoy revisando, seguir acá
        </button>
      </div>
    </div>
  )
}
