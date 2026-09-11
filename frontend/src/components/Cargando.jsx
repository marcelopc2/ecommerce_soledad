/* Rueda chica para los botones que están esperando una respuesta.
 *
 * Los botones ya cambiaban el texto ("Procesando…"), pero un texto quieto no
 * distingue entre "está trabajando" y "se colgó": justo la duda que aparece
 * cuando se acaba de apretar Pagar. Girando, se ve que algo sigue pasando.
 *
 * Hereda el color del botón (currentColor), así sirve en el amarillo, en el
 * morado y en los de borde sin tener una versión por cada uno. */
export default function Cargando({ size = 16 }) {
  return (
    <span
      className="cargando-rueda"
      style={{ width: size, height: size }}
      /* El texto del botón ya dice qué está pasando; si esto también se
         anunciara, el lector de pantalla lo repetiría dos veces. */
      aria-hidden="true"
    />
  )
}
