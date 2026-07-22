// Botón flotante (abajo a la izquierda) que abre un chat de WhatsApp con
// mensaje precargado. Es solo un link a wa.me — no usa la API de WhatsApp
// Business, así que no requiere cuenta verificada ni backend.
const NUMERO = '56985026926' // +56 9 8502 6926, mismo teléfono de "Contacto"
const MENSAJE = '¡Hola! Quería hacer una consulta sobre Ingenio Blocks.'

export default function WhatsAppButton() {
  const href = `https://wa.me/${NUMERO}?text=${encodeURIComponent(MENSAJE)}`

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="whatsapp-btn"
      aria-label="Escríbenos por WhatsApp"
    >
      <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 0 0 4.74 1.21h.01c5.46 0 9.9-4.45 9.9-9.91C21.95 6.45 17.5 2 12.04 2zm5.8 14.03c-.24.68-1.42 1.3-1.96 1.35-.5.05-1.13.08-1.83-.11-.42-.12-.96-.3-1.65-.6-2.9-1.25-4.8-4.16-4.94-4.36-.15-.19-1.18-1.57-1.18-3 0-1.42.75-2.12 1.02-2.42.27-.29.58-.36.78-.36.19 0 .39 0 .56.01.18.01.42-.07.65.5.24.58.82 2 .89 2.15.07.15.12.32.02.52-.09.19-.14.31-.28.48-.14.17-.29.37-.42.5-.14.14-.28.29-.12.57.15.29.68 1.13 1.47 1.83 1.01.9 1.87 1.18 2.15 1.31.29.14.46.12.63-.07.17-.19.72-.84.92-1.13.19-.29.39-.24.65-.14.27.1 1.68.79 1.97.94.29.14.48.21.55.33.07.12.07.68-.17 1.36z" />
      </svg>
    </a>
  )
}
