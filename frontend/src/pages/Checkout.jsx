import { useState, useEffect } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { api } from '../api'
import Header from '../components/Header'

const clp = (n) => '$' + parseInt(n).toLocaleString('es-CL')

export default function Checkout() {
  const location = useLocation()
  const product = location.state?.product
  const isDigital = product?.is_digital

  const [contact, setContact] = useState({ name: '', email: '', phone: '' })
  const [regions, setRegions] = useState([])
  const [region, setRegion] = useState('')
  const [commune, setCommune] = useState('')
  const [address, setAddress] = useState({ street: '', number: '', detail: '' })
  const [quotes, setQuotes] = useState([])
  const [quoting, setQuoting] = useState(false)
  const [quoteMsg, setQuoteMsg] = useState('')
  const [courier, setCourier] = useState(null) // {courier, service, price, days}
  const [paying, setPaying] = useState(false)

  useEffect(() => {
    if (product && !isDigital) {
      api.get('/shipping/communes/')
        .then(res => setRegions(res.data.regions || []))
        .catch(err => console.error('Error cargando comunas:', err))
    }
  }, [product, isDigital])

  if (!product) {
    return (
      <div className="App">
        <Header />
        <div className="checkout">
          <p>No hay ningún producto seleccionado.</p>
          <Link to="/" className="back-link">← Volver al catálogo</Link>
        </div>
      </div>
    )
  }

  const communesForRegion = regions.find(r => r.region === region)?.communes || []

  const handleQuote = () => {
    if (!commune) return
    setQuoting(true); setQuoteMsg(''); setQuotes([]); setCourier(null)
    api.post('/shipping/quote/', { product_ids: [product.id], commune, commune_name: commune })
      .then(res => {
        if (res.data.quotes && res.data.quotes.length) {
          setQuotes(res.data.quotes)
        } else {
          setQuoteMsg('No hay tarifas disponibles para esa comuna.')
        }
      })
      .catch(() => setQuoteMsg('Error al cotizar el envío. Intenta de nuevo.'))
      .finally(() => setQuoting(false))
  }

  const productPrice = parseInt(product.price)
  const shippingPrice = courier ? courier.price : 0
  const total = productPrice + shippingPrice

  const contactComplete = contact.name && contact.email && contact.phone
  const deliveryComplete = isDigital ||
    (region && commune && address.street && address.number && courier)
  const canPay = contactComplete && deliveryComplete && !paying

  const handleCheckout = async (gateway) => {
    setPaying(true)
    const payload = { product_ids: [product.id], email: contact.email }
    if (!isDigital) {
      payload.shipping = {
        recipient_name: contact.name,
        recipient_phone: contact.phone,
        recipient_email: contact.email,
        region, commune, commune_id: null,
        address_street: address.street,
        address_number: address.number,
        address_detail: address.detail,
        courier: courier.courier,
        service_name: courier.service,
        shipping_cost: courier.price,
      }
    }
    try {
      const url = gateway === 'webpay' ? '/payments/create/' : '/payments/mp-create/'
      const { data } = await api.post(url, payload)
      if (gateway === 'webpay') {
        // Transbank exige un form POST con el token.
        const form = document.createElement('form')
        form.method = 'POST'
        form.action = data.url
        const input = document.createElement('input')
        input.type = 'hidden'; input.name = 'token_ws'; input.value = data.token
        form.appendChild(input)
        document.body.appendChild(form)
        form.submit()
      } else {
        window.location.href = data.url
      }
    } catch (err) {
      alert(err.response?.data?.error || 'Error al iniciar el pago')
      setPaying(false)
    }
  }

  return (
    <div className="App">
      <Header />
      <div className="checkout">
        <Link to="/" className="back-link">← Seguir comprando</Link>
        <h2 className="checkout-title">Finalizar compra</h2>

        <div className="checkout-grid">
          {/* Columna izquierda: formulario */}
          <div className="checkout-form">

            {/* Paso 1: Contacto */}
            <section className="step">
              <h3>1. Tus datos</h3>
              <input className="field" placeholder="Nombre completo"
                value={contact.name} onChange={e => setContact({ ...contact, name: e.target.value })} />
              <input className="field" type="email" placeholder="Email"
                value={contact.email} onChange={e => setContact({ ...contact, email: e.target.value })} />
              <input className="field" placeholder="Teléfono (ej. +56 9 1234 5678)"
                value={contact.phone} onChange={e => setContact({ ...contact, phone: e.target.value })} />
            </section>

            {/* Paso 2: Entrega (solo productos físicos) */}
            {isDigital ? (
              <section className="step">
                <h3>2. Entrega</h3>
                <p className="digital-note">📦 Este es un producto digital: recibirás el acceso por email, sin envío.</p>
              </section>
            ) : (
              <section className="step">
                <h3>2. Dirección de envío</h3>
                <div className="row">
                  <select className="field" value={region}
                    onChange={e => { setRegion(e.target.value); setCommune(''); setQuotes([]); setCourier(null) }}>
                    <option value="">Región…</option>
                    {regions.map(r => <option key={r.region} value={r.region}>{r.region}</option>)}
                  </select>
                  <select className="field" value={commune} disabled={!region}
                    onChange={e => { setCommune(e.target.value); setQuotes([]); setCourier(null) }}>
                    <option value="">Comuna…</option>
                    {communesForRegion.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </select>
                </div>
                <div className="row">
                  <input className="field" placeholder="Calle"
                    value={address.street} onChange={e => setAddress({ ...address, street: e.target.value })} />
                  <input className="field field-sm" placeholder="Número"
                    value={address.number} onChange={e => setAddress({ ...address, number: e.target.value })} />
                </div>
                <input className="field" placeholder="Depto / oficina / referencia (opcional)"
                  value={address.detail} onChange={e => setAddress({ ...address, detail: e.target.value })} />

                <button className="btn-secondary" onClick={handleQuote} disabled={!commune || quoting}>
                  {quoting ? 'Cotizando…' : 'Cotizar envío'}
                </button>

                {quoteMsg && <p className="quote-msg">{quoteMsg}</p>}

                {quotes.length > 0 && (
                  <div className="quotes">
                    {quotes.map(q => (
                      <label key={q.courier + q.service} className={'quote-option' + (courier === q ? ' selected' : '')}>
                        <input type="radio" name="courier"
                          checked={courier === q} onChange={() => setCourier(q)} />
                        <span className="quote-courier">{q.courier} · {q.service}</span>
                        <span className="quote-days">{q.days}</span>
                        <span className="quote-price">{clp(q.price)}</span>
                      </label>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>

          {/* Columna derecha: resumen */}
          <aside className="summary">
            <h3>Resumen</h3>
            <div className="summary-row"><span>{product.name}</span><span>{clp(productPrice)}</span></div>
            {!isDigital && (
              <div className="summary-row">
                <span>Envío {courier ? `(${courier.courier})` : ''}</span>
                <span>{courier ? clp(shippingPrice) : '—'}</span>
              </div>
            )}
            <div className="summary-row total"><span>Total</span><span>{clp(total)}</span></div>

            <div className="pay-buttons">
              <button className="btn-webpay" disabled={!canPay} onClick={() => handleCheckout('webpay')}>
                💳 Pagar con Webpay
              </button>
              <button className="btn-mp" disabled={!canPay} onClick={() => handleCheckout('mercadopago')}>
                🤝 Pagar con MercadoPago
              </button>
            </div>
            {!canPay && !paying && (
              <p className="pay-hint">
                {!contactComplete ? 'Completa tus datos' : 'Elige región, comuna, dirección y courier'}
              </p>
            )}
          </aside>
        </div>
      </div>
    </div>
  )
}
