import { useEffect, useState } from 'react'
import { api, PANEL_URL } from './api'
import TEXTOS_ORIGINALES from './textosPortada.json'
import { TEMAS } from './temas'

// Además de los textos: las fotos (null = la del diseño) y la temporada.
const ORIGINALES = { ...TEXTOS_ORIGINALES, hero_imagen: null, quienes_imagen: null, tema: 'normal' }

/* Textos fijos de la portada que se editan en el panel (Portada → Textos de la
   portada). Se piden UNA vez y se comparten: la portada, el contacto y el pie
   los usan, y el pie sale también en las páginas legales.

   ORIGINALES es copia de catalog/textos_portada.json (una prueba del servidor
   avisa si se desalinean): si la API no responde, la portada sale igual, con
   los textos de siempre. */
let cargados = null
let pedido = null
let delPanel = false   // en la vista previa, lo escrito en el panel manda
const oyentes = new Set()

function publicar(textos) {
  delPanel = true
  cargados = textos
  oyentes.forEach(avisar => avisar(textos))
}

export function cargarTextos() {
  if (!pedido) {
    pedido = api.get('/catalog/textos/')
      .then(({ data }) => { if (!delPanel) cargados = { ...ORIGINALES, ...data } })
      .catch(() => { if (!cargados) cargados = ORIGINALES })
      .then(() => cargados || ORIGINALES)
  }
  return pedido
}

export function useTextos() {
  const [textos, setTextos] = useState(cargados || ORIGINALES)
  useEffect(() => {
    let vivo = true
    oyentes.add(setTextos)
    cargarTextos().then(t => { if (vivo) setTextos(t) })
    return () => { vivo = false; oyentes.delete(setTextos) }
  }, [])
  return textos
}

/* ---------------------------------------------------------------------------
   Vista previa del panel: la página "Textos de la portada" muestra esta misma
   portada en un iframe con ?vista_previa=1 y le manda lo que se va escribiendo.
   Solo se aceptan mensajes del panel (mismo origen que PANEL_URL) y solo
   textos (nada de HTML: se pintan como texto, igual que los guardados), así
   que otra página no puede usar esto para meter contenido.
   --------------------------------------------------------------------------- */
export const enVistaPrevia = typeof window !== 'undefined'
  && window.parent !== window
  && new URLSearchParams(window.location.search).has('vista_previa')

/** Dónde está cada sección del panel en la portada (ver catalog/textos_portada.py). */
const SECCIONES_VISTA_PREVIA = {
  hero: '.lp-hero',
  fotos: '.lp-hero',
  como: '#como-funciona',
  beneficios: '#beneficios',
  productos: '#kits',
  quienes: '#quienes-somos',
  testimonios: '.lp-testimonios',
  contacto: '#contacto',
  pie: '.lp-footer',
}

if (enVistaPrevia) {
  const origenPanel = new URL(PANEL_URL, window.location.href).origin
  let ultimaSeccion = null

  window.addEventListener('message', (e) => {
    if (e.origin !== origenPanel || e.data?.tipo !== 'ib-textos') return
    const recibidos = e.data.textos || {}
    const textos = { ...ORIGINALES, ...(cargados || {}) }
    for (const clave of Object.keys(TEXTOS_ORIGINALES)) {
      textos[clave] = typeof recibidos[clave] === 'string' && recibidos[clave].trim()
        ? recibidos[clave] : TEXTOS_ORIGINALES[clave]
    }
    if (recibidos.tema in TEMAS || recibidos.tema === 'normal') textos.tema = recibidos.tema
    // Fotos: '' = volver a la original; una foto recién elegida llega como
    // data:image/…, que no puede traer código. Cualquier otra cosa se ignora.
    for (const clave of ['hero_imagen', 'quienes_imagen']) {
      const v = recibidos[clave]
      if (v === '') textos[clave] = null
      else if (typeof v === 'string' && v.startsWith('data:image/')) textos[clave] = v
    }
    publicar(textos)

    const selector = SECCIONES_VISTA_PREVIA[e.data.seccion]
    if (selector && e.data.seccion !== ultimaSeccion) {
      ultimaSeccion = e.data.seccion
      document.querySelectorAll('.lp-editando').forEach(el => el.classList.remove('lp-editando'))
      const el = document.querySelector(selector)
      if (el) {
        el.classList.add('lp-editando')
        // scrollTo y no scrollIntoView: ese también mueve la página que
        // contiene el iframe, y el panel saltaba hacia abajo en cada sección.
        window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY, behavior: 'smooth' })
      }
    }
  })
  // Avisa que ya escucha: el panel recién ahí manda lo que hay escrito.
  window.addEventListener('load', () => window.parent.postMessage({ tipo: 'ib-vista-lista' }, origenPanel))
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
    <p key={i}><Resaltado texto={p.replace(/ (\S+)$/, ' $1')} clase={clase} /></p>
  ))
}
