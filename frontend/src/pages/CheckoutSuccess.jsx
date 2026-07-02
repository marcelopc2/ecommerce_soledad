import { useSearchParams, Link } from 'react-router-dom'
import Header from '../components/Header'

export default function CheckoutSuccess() {
  const [params] = useSearchParams()
  const order = params.get('order')

  return (
    <div className="App">
      <Header />
      <div className="result-card success">
        <div className="result-icon">✅</div>
        <h1>¡Pago exitoso!</h1>
        <p>Tu pedido fue confirmado. Te enviaremos los detalles por email.</p>
        {order && <p className="order-id">N° de orden: <strong>{order}</strong></p>}
        <Link to="/" className="btn-primary link-btn">Volver a la tienda</Link>
      </div>
    </div>
  )
}
