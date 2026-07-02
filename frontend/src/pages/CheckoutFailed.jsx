import { useSearchParams, Link } from 'react-router-dom'
import Header from '../components/Header'

const REASONS = {
  aborted: 'Cancelaste el pago.',
  rejected: 'El pago fue rechazado por el medio de pago.',
  invalid_token: 'No pudimos validar la transacción.',
  invalid_order: 'No encontramos la orden.',
  amount_mismatch: 'El monto pagado no coincide con el pedido.',
  error: 'Ocurrió un error al procesar el pago.',
}

export default function CheckoutFailed() {
  const [params] = useSearchParams()
  const reason = params.get('reason')
  const message = REASONS[reason] || 'El pago no se completó.'

  return (
    <div className="App">
      <Header />
      <div className="result-card failed">
        <div className="result-icon">❌</div>
        <h1>El pago no se completó</h1>
        <p>{message}</p>
        <p className="result-help">No te preocupes, no se realizó ningún cobro. Puedes intentar de nuevo.</p>
        <Link to="/" className="btn-primary link-btn">Volver a la tienda</Link>
      </div>
    </div>
  )
}
