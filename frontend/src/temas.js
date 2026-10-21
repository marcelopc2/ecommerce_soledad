/* Adornos de temporada de la portada principal (se eligen en el panel:
   Portada → Textos, fotos y temporada). Las claves son las de
   catalog.models.TextosPortada.TEMAS; una que no esté acá se ve normal.

   - flotan: los que reemplazan a las chispitas y crucecitas del diseño.
   - lluvia: los que cruzan la portada, cayendo (copos) o subiendo (globos).

   Son emojis a propósito: se ven en todos los equipos sin cargar imágenes
   extra y cambiar un tema es cambiar una línea. */
export const TEMAS = {
  ano_nuevo: { flotan: ['🎆', '🥂', '✨', '🎉'], lluvia: ['🎊', '✨'], sentido: 'cae' },
  verano: { flotan: ['☀️', '🏖️', '🍉', '🕶️', '🌊'] },
  san_valentin: { flotan: ['💜', '💛', '💌', '💕'], lluvia: ['💜', '💛'], sentido: 'sube' },
  vuelta_clases: { flotan: ['✏️', '📚', '🎒', '📐', '🖍️'] },
  pascua: { flotan: ['🥚', '🐰', '🌷', '🐣'] },
  dia_madre: { flotan: ['💐', '🌸', '💜', '🌷'], lluvia: ['🌸'], sentido: 'cae' },
  dia_padre: { flotan: ['🔧', '👔', '🏆', '💙'] },
  invierno: { flotan: ['☔', '🧣', '☕', '⛄'], lluvia: ['❄️'], sentido: 'cae' },
  dia_nino: { flotan: ['🧸', '🎁', '🪁', '⭐'], lluvia: ['🎈'], sentido: 'sube' },
  fiestas_patrias: { flotan: ['🇨🇱', '⭐', '🥟', '🎠'], lluvia: ['🪁'], sentido: 'sube' },
  halloween: { flotan: ['🦇', '🎃', '👻', '🕸️', '🍬', '🦇'], lluvia: ['🦇'], sentido: 'sube' },
  navidad: { flotan: ['🎄', '⭐', '🎁', '🔔', '⛄'], lluvia: ['❄️'], sentido: 'cae' },
}
