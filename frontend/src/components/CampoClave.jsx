import { useState } from 'react'

/* Campo de contraseña con el ojo para verla.
 *
 * Existe como componente y no repetido en cada pantalla porque son seis campos
 * en tres páginas, y el comportamiento tiene detalles fáciles de olvidar en una
 * copia: que el botón NO envíe el formulario, que el lector de pantalla anuncie
 * el estado, y que al mostrarla el navegador no la guarde como texto.
 *
 * Recibe las mismas props que un <input> normal, así reemplaza al que había sin
 * tocar el resto de la pantalla ni sus estilos. */
export default function CampoClave({ className = '', ...props }) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="campo-clave">
      <input
        {...props}
        type={visible ? 'text' : 'password'}
        className={`campo-clave-input ${className}`.trim()}
      />
      {/* type="button" es imprescindible: sin él un <button> dentro de un
          formulario lo ENVÍA, así que mirar la clave intentaría entrar.
          tabIndex -1 porque al tabular desde el campo se espera llegar al botón
          de entrar, no a un control auxiliar. */}
      <button
        type="button"
        className="campo-clave-ojo"
        onClick={() => setVisible(v => !v)}
        tabIndex={-1}
        aria-label={visible ? 'Ocultar la contraseña' : 'Mostrar la contraseña'}
        aria-pressed={visible}
        title={visible ? 'Ocultar' : 'Mostrar'}
      >
        {visible ? <IconOjoTachado /> : <IconOjo />}
      </button>
    </div>
  )
}

const IconOjo = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12z" />
    <circle cx="12" cy="12" r="3.2" />
  </svg>
)

const IconOjoTachado = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9.9 5.7A9.9 9.9 0 0 1 12 5.5c7 0 10.5 6.5 10.5 6.5a18 18 0 0 1-3.3 4.2M6.2 6.7A18 18 0 0 0 1.5 12S5 18.5 12 18.5c1.9 0 3.5-.5 4.9-1.2" />
    <path d="M9.8 9.9a3.2 3.2 0 0 0 4.4 4.4" />
    <line x1="2.5" y1="2.5" x2="21.5" y2="21.5" />
  </svg>
)
