import { useState, useEffect } from 'react'

// Botón flotante (abajo a la derecha) que aparece al bajar y lleva al inicio.
export default function ScrollTopButton() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 500)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const toTop = () => {
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' })
  }

  return (
    <button
      className={'scroll-top' + (show ? ' visible' : '')}
      onClick={toTop}
      aria-label="Volver arriba"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 19V5M5 12l7-7 7 7" />
      </svg>
    </button>
  )
}
