import { useState, useEffect, useRef, useMemo } from 'react'

/**
 * Combobox buscable: un input donde se escribe para filtrar una lista larga.
 *
 * Toda la data (regiones/comunas) ya viene cargada en el cliente, así que el
 * filtrado es instantáneo y NO va al servidor por cada tecla. Con 727 comunas
 * un <select> nativo es incómodo; esto deja escribir "provi" y ver Providencia.
 *
 * Props:
 *   options      [{ label, ...extra }]  — la lista a filtrar
 *   value        string | null          — el label actualmente elegido
 *   onSelect     (option) => void       — recibe la opción completa elegida
 *   placeholder, disabled, id
 *
 * El valor "real" es la opción elegida, no lo que se escribe: si alguien
 * escribe algo que no coincide y cierra, se revierte a la última elección
 * válida (no se puede quedar con texto libre, porque necesitamos el id real).
 */

function normaliza(texto) {
  return (texto || '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '') // saca tildes (marcas diacriticas)
    .toLowerCase().trim()
}

export default function Combobox({ options, value, onSelect, placeholder, disabled, id }) {
  const [abierto, setAbierto] = useState(false)
  const [query, setQuery] = useState(value || '')
  const [resaltado, setResaltado] = useState(0)
  const contenedorRef = useRef(null)
  const listaRef = useRef(null)

  // Si el valor elegido cambia desde afuera (ej. al cambiar de región se limpia
  // la comuna), el input refleja ese cambio.
  useEffect(() => { setQuery(value || '') }, [value])

  // Mientras está abierto se filtra por lo escrito; cerrado muestra la elección.
  const filtradas = useMemo(() => {
    if (!abierto) return options
    const q = normaliza(query)
    if (!q) return options
    return options.filter(o => normaliza(o.label).includes(q))
  }, [options, query, abierto])

  // Cerrar al hacer click afuera, revirtiendo el texto al valor válido.
  useEffect(() => {
    if (!abierto) return
    const alClickAfuera = (e) => {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target)) {
        cerrarSinElegir()
      }
    }
    document.addEventListener('mousedown', alClickAfuera)
    return () => document.removeEventListener('mousedown', alClickAfuera)
  }, [abierto, value])

  // Mantener la opción resaltada visible al navegar con el teclado.
  useEffect(() => {
    if (!abierto || !listaRef.current) return
    const el = listaRef.current.children[resaltado]
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [resaltado, abierto])

  const abrir = () => {
    if (disabled) return
    setAbierto(true)
    setQuery('')          // se vacía para poder escribir de cero
    setResaltado(0)
  }

  const cerrarSinElegir = () => {
    setAbierto(false)
    setQuery(value || '')  // vuelve al último valor válido
  }

  const elegir = (opcion) => {
    onSelect(opcion)
    setQuery(opcion.label)
    setAbierto(false)
  }

  const alEscribir = (e) => {
    setQuery(e.target.value)
    setAbierto(true)
    setResaltado(0)
  }

  const alTecla = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!abierto) { abrir(); return }
      setResaltado(i => Math.min(i + 1, filtradas.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setResaltado(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (abierto && filtradas[resaltado]) elegir(filtradas[resaltado])
    } else if (e.key === 'Escape') {
      cerrarSinElegir()
    }
  }

  return (
    <div className="cbx" ref={contenedorRef}>
      <input
        id={id}
        className="cbx-input"
        type="text"
        role="combobox"
        aria-expanded={abierto}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={query}
        onChange={alEscribir}
        onFocus={abrir}
        onKeyDown={alTecla}
      />
      <span className="cbx-flecha" aria-hidden="true">▾</span>

      {abierto && (
        <ul className="cbx-lista" role="listbox" ref={listaRef}>
          {filtradas.length === 0 && <li className="cbx-vacio">Sin resultados</li>}
          {filtradas.map((o, i) => (
            <li
              key={o.label}
              role="option"
              aria-selected={o.label === value}
              className={'cbx-opcion' + (i === resaltado ? ' resaltada' : '') + (o.label === value ? ' elegida' : '')}
              // onMouseDown (no onClick): se dispara antes que el blur/click-afuera,
              // así la elección se registra en vez de perderse al cerrar.
              onMouseDown={(e) => { e.preventDefault(); elegir(o) }}
              onMouseEnter={() => setResaltado(i)}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
