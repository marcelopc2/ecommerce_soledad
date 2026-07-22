import { useSearchParams, Link } from 'react-router-dom'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './landing.css'
import './resultado.css'

const IconAlerta = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.01" />
  </svg>
)

/* Cada motivo trae su explicación y si hubo o no cobro. Es la primera pregunta
   de quien llega acá, y decirlo mal (o no decirlo) genera un reclamo. */
const MOTIVOS = {
  aborted: {
    titulo: 'Cancelaste el pago',
    texto: 'No se realizó ningún cobro. Tu pedido quedó sin confirmar.',
    cobro: 'no',
  },
  rejected: {
    titulo: 'El pago fue rechazado',
    texto: 'Tu banco o el medio de pago no autorizó la transacción. Suele pasar por saldo, límite de compras por internet o datos mal ingresados.',
    cobro: 'no',
  },
  invalid_token: {
    titulo: 'No pudimos validar la transacción',
    texto: 'La sesión de pago venció o el enlace ya se había usado.',
    cobro: 'no',
  },
  invalid_order: {
    titulo: 'No encontramos el pedido',
    texto: 'No pudimos identificar la compra asociada a este pago.',
    cobro: 'revisar',
  },
  amount_mismatch: {
    titulo: 'El monto no coincide',
    texto: 'El valor pagado no calza con el del pedido, así que lo detuvimos por seguridad.',
    cobro: 'revisar',
  },
  // Este es el caso del corte de red durante el cobro: NO podemos afirmar que
  // no se cobró, porque puede haberse cobrado igual (ver payments/views.py).
  error: {
    titulo: 'Algo falló al procesar el pago',
    texto: 'Tuvimos un problema de conexión con el medio de pago mientras se confirmaba la transacción.',
    cobro: 'revisar',
  },
}

// Mismo número que el botón flotante y la sección de contacto.
const WHATSAPP = 'https://wa.me/56985026926?text=' + encodeURIComponent(
  'Hola, tuve un problema al pagar en Ingenio Blocks y necesito ayuda.'
)

const POR_DEFECTO = {
  titulo: 'El pago no se completó',
  texto: 'No pudimos confirmar la transacción.',
  cobro: 'revisar',
}

export default function CheckoutFailed() {
  const [params] = useSearchParams()
  const motivo = MOTIVOS[params.get('reason')] || POR_DEFECTO

  return (
    <div className="lp">
      <div className="res-page res-error">
        <div className="res-top">
          <div className="res-top-inner">
            <Link to="/" className="res-logo">
              <img src={logo} alt="Ingenio Blocks" />
            </Link>
          </div>
        </div>

        <div className="res-wrap">
          <div className="res-card">
            <div className="res-emblema"><IconAlerta /></div>
            <h1>{motivo.titulo}</h1>
            <p className="res-bajada">{motivo.texto}</p>

            <ol className="res-pasos">
              <li className="res-paso">
                <span className="res-paso-num">1</span>
                <div>
                  <h3>
                    {motivo.cobro === 'no'
                      ? 'No te cobramos nada'
                      : 'Revisa tu cartola antes de reintentar'}
                  </h3>
                  <p>
                    {motivo.cobro === 'no' ? (
                      'Tu tarjeta no registró ningún movimiento. Puedes intentarlo otra vez cuando quieras.'
                    ) : (
                      <>
                        En casos como este el cobro <strong>puede haberse
                        realizado igual</strong>. Antes de pagar de nuevo, revisa
                        tu cartola o escríbenos: si quedó cobrado, activamos tu
                        compra sin que pagues dos veces.
                      </>
                    )}
                  </p>
                </div>
              </li>
              <li className="res-paso">
                <span className="res-paso-num">2</span>
                <div>
                  <h3>Vuelve a intentarlo</h3>
                  <p>
                    Tu carrito no se perdió. Puedes elegir otro medio de pago
                    (Webpay o MercadoPago) desde la página de kits.
                  </p>
                </div>
              </li>
            </ol>

            <div className="res-acciones">
              <Link to="/#kits" className="res-btn res-btn-principal">
                Volver a intentar
              </Link>
              <a
                href={WHATSAPP}
                target="_blank"
                rel="noreferrer"
                className="res-btn res-btn-secundario"
              >
                Escríbenos por WhatsApp
              </a>
            </div>

            <p className="res-ayuda">
              También puedes escribirnos a{' '}
              <a href="mailto:contacto@ingenioblocks.com">contacto@ingenioblocks.com</a>{' '}
              y te ayudamos a completar la compra.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
