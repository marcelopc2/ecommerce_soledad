// El overlay de carga vive en index.html, AFUERA del árbol de React (ver el
// comentario ahí). Esta función es la única forma de hacerlo desaparecer.
// Sticky a propósito: una vez oculto no debe reaparecer en navegaciones
// internas de la SPA, solo cubre la carga inicial de la página.
let ocultado = false

export function ocultarPreloader() {
  if (ocultado) return
  ocultado = true
  const el = document.getElementById('pre')
  if (!el) return
  el.classList.add('oculto')
  el.addEventListener('transitionend', () => el.remove(), { once: true })
}
