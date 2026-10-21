import { useEffect, useState } from 'react'
import { api } from './api'
import ORIGINALES from './textosPortada.json'

/* Textos fijos de la portada que se editan en el panel (Portada → Textos de la
   portada). Se piden UNA vez y se comparten: la portada, el contacto y el pie
   los usan, y el pie sale también en las páginas legales.

   ORIGINALES es copia de catalog/textos_portada.json (una prueba del servidor
   avisa si se desalinean): si la API no responde, la portada sale igual, con
   los textos de siempre. */
let cargados = null
let pedido = null

export function cargarTextos() {
  if (!pedido) {
    pedido = api.get('/catalog/textos/')
      .then(({ data }) => { cargados = { ...ORIGINALES, ...data } })
      .catch(() => { cargados = ORIGINALES })
      .then(() => cargados)
  }
  return pedido
}

export function useTextos() {
  const [textos, setTextos] = useState(cargados || ORIGINALES)
  useEffect(() => {
    let vivo = true
    cargarTextos().then(t => { if (vivo) setTextos(t) })
    return () => { vivo = false }
  }, [])
  return textos
}

/* "la **experiencia** de…": lo que va entre dobles asteriscos sale resaltado
   con `clase`. Es lo único que se interpreta: el texto no se trata como HTML,
   así que nada de lo que se escriba en el panel puede meter código. */
export function Resaltado({ texto, clase = 'lp-purple-text', como: Etiqueta = 'strong' }) {
  return (texto || '').split('**').map((trozo, i) =>
    i % 2 ? <Etiqueta key={i} className={clase}>{trozo}</Etiqueta> : trozo)
}

/* Párrafos separados por una línea en blanco. Las dos últimas palabras de cada
   uno van unidas por un espacio duro, para que nunca quede una sola palabra
   colgando en la última línea (pasaba con "ritmo." según el ancho). */
export function Parrafos({ texto, clase }) {
  return (texto || '').split(/\n\s*\n/).map(p => p.trim()).filter(Boolean).map((p, i) => (
    <p key={i}><Resaltado texto={p.replace(/ (\S+)$/, '\u00a0$1')} clase={clase} /></p>
  ))
}
