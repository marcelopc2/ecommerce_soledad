import { useSearchParams, Link } from 'react-router-dom'
import { useAuth } from '../auth'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './landing.css'
import './resultado.css'

const IconCheck = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6L9 17l-5-5" />
  </svg>
)

export default function CheckoutSuccess() {
  const [params] = useSearchParams()
  const { user } = useAuth()
  const orden = params.get('order')

  return (
    <div className="lp">
      <div className="res-page res-ok">
        <div className="res-top">
          <div className="res-top-inner">
            <Link to="/" className="res-logo">
              <img src={logo} alt="Ingenio Blocks" />
            </Link>
          </div>
        </div>

        <div className="res-wrap">
          <div className="res-card">
            <div className="res-emblema"><IconCheck /></div>
            <h1>¡Listo, recibimos tu pago!</h1>
            <p className="res-bajada">
              Ya está todo confirmado. Te contamos qué sigue para que no te quedes
              con dudas.
            </p>
            {orden && (
              <span className="res-orden">
                N° de pedido: <strong>{orden.slice(0, 8)}</strong>
              </span>
            )}

            {/* El correo es el paso crítico: si cae en spam el cliente queda sin
                forma de entrar al aula, y ese es el reclamo más caro que hay. */}
            <ol className="res-pasos">
              {!user && (
                <li className="res-paso">
                  <span className="res-paso-num">1</span>
                  <div>
                    <h3>Revisa tu correo</h3>
                    <p>
                      Te enviamos un mensaje al correo que nos diste para que{' '}
                      <span className="res-destacado">crees tu contraseña</span> y
                      entres al Aula Virtual. Si no lo ves en unos minutos,
                      búscalo en <strong>spam</strong> o correo no deseado.
                    </p>
                  </div>
                </li>
              )}
              <li className="res-paso">
                <span className="res-paso-num">{user ? '1' : '2'}</span>
                <div>
                  <h3>Entra al Aula Virtual</h3>
                  <p>
                    Ahí están tus modelos con las instrucciones paso a paso. Se
                    libera <span className="res-destacado">un modelo nuevo cada
                    semana</span>, y para pasar al siguiente hay que completar el
                    anterior.
                  </p>
                </div>
              </li>
              <li className="res-paso">
                <span className="res-paso-num">{user ? '2' : '3'}</span>
                <div>
                  <h3>Si compraste el kit físico</h3>
                  <p>
                    Preparamos tu despacho y te avisamos por correo con el número
                    de seguimiento apenas salga. Los planes y modelos extra son
                    digitales: quedan disponibles al instante.
                  </p>
                </div>
              </li>
            </ol>

            <div className="res-acciones">
              <Link to="/mis-cursos" className="res-btn res-btn-principal">
                Ir a mi Aula Virtual
              </Link>
              <Link to="/" className="res-btn res-btn-secundario">
                Volver al inicio
              </Link>
            </div>

            <p className="res-ayuda">
              ¿No te llegó el correo o algo no cuadra? Escríbenos a{' '}
              <a href="mailto:contacto@ingenioblocks.com">contacto@ingenioblocks.com</a>{' '}
              con tu número de pedido y lo resolvemos.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
