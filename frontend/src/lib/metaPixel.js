// Píxel de Meta (Facebook/Instagram): le cuenta a Meta quién vio la página,
// empezó a comprar y compró, para que las campañas puedan medir ventas.
//
// Solo se carga en el dominio real. En localhost, en la IP del servidor o en
// la vista previa del panel no se manda NADA a Meta: una prueba local no puede
// ensuciar las métricas de las campañas (ni contar compras de mentira).
import { enVistaPrevia } from '../textos'

const ID = import.meta.env.VITE_META_PIXEL_ID || ''
const DOMINIOS = ['ingenioblocks.com', 'www.ingenioblocks.com']

const activo = () =>
  !!ID && typeof window !== 'undefined' && !enVistaPrevia &&
  DOMINIOS.includes(window.location.hostname)

let cargado = false

function cargar() {
  if (cargado) return true
  if (!activo()) return false
  // El código base que entrega Meta, tal cual (sin el PageView: ese lo manda
  // el router en cada cambio de página, ver App.jsx).
  !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
  n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
  document,'script','https://connect.facebook.net/en_US/fbevents.js');
  window.fbq('init', ID)
  cargado = true
  return true
}

/** Manda un evento estándar de Meta. Si el píxel no corresponde, no hace nada. */
export function evento(nombre, datos, opciones) {
  if (!cargar()) return
  try {
    window.fbq('track', nombre, datos || {}, opciones || {})
  } catch {
    // Un bloqueador de anuncios puede romper fbq: la compra no puede fallar por eso.
  }
}

// La compra se avisa en la página de "¡Listo!", que llega de vuelta desde
// Transbank o Mercado Pago. Para saber cuánto fue, el checkout deja anotado el
// monto justo antes de mandar a pagar.
const CLAVE = 'ib_compra_meta'

export function anotarCompra(datos) {
  try { sessionStorage.setItem(CLAVE, JSON.stringify(datos)) } catch { /* sin storage: no se mide */ }
}

/** Avisa la compra UNA vez por pedido (recargar la página no la duplica). */
export function avisarCompra(orden) {
  if (!orden) return
  let datos = null
  try {
    datos = JSON.parse(sessionStorage.getItem(CLAVE) || 'null')
    sessionStorage.removeItem(CLAVE)
  } catch { /* sin storage: no se sabe el monto */ }
  if (!datos) return
  try {
    const avisadas = JSON.parse(localStorage.getItem('ib_compras_avisadas') || '[]')
    if (avisadas.includes(orden)) return
    localStorage.setItem('ib_compras_avisadas', JSON.stringify([...avisadas, orden].slice(-20)))
  } catch { /* sin storage: se avisa igual */ }
  // eventID = n° de pedido: si más adelante se avisan las compras también desde
  // el servidor, Meta las junta en vez de contarlas dos veces.
  evento('Purchase', datos, { eventID: orden })
}
