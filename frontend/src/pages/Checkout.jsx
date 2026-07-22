import { useState, useEffect } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import Combobox from '../components/Combobox'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './landing.css'
import './checkout.css'

const clp = (n) => '$' + parseInt(n, 10).toLocaleString('es-CL')

/* ---------- Validaciones ----------
   Mismas reglas que el servidor (payments/serializers.py). Acá son solo para
   avisar al instante; la validación que decide es la del backend, porque estas
   se saltan con un POST directo. */

function errorNombre(v, que) {
  const t = (v || '').trim()
  if (!t) return `Falta el ${que}.`
  if (t.length < 2) return `Escribe el ${que} completo.`
  if (/\d/.test(t)) return `El ${que} no puede tener números.`
  return ''
}

function errorEmail(v) {
  const t = (v || '').trim()
  if (!t) return 'Falta el correo.'
  // Chequeo simple a propósito: el estándar real es enorme y validar de más
  // rechaza correos válidos. El servidor hace la validación estricta.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(t)) return 'Escribe un correo válido (nombre@correo.cl).'
  return ''
}

function errorTelefono(v) {
  let d = (v || '').replace(/\D/g, '')
  if (!d) return 'Falta el teléfono.'
  if (d.startsWith('56')) d = d.slice(2)
  if (d.length !== 9) return 'Debe tener 9 dígitos, por ejemplo +56 9 1234 5678.'
  if (d[0] === '0') return 'El número no puede empezar en 0.'
  return ''
}

function errorTexto(v, msg) {
  return (v || '').trim() ? '' : msg
}

function Cabecera({ titulo }) {
  return (
    <div className="co-top">
      <div className="co-top-inner">
        <Link to="/" className="co-logo" aria-label="Ir al inicio">
          <img src={logo} alt="Ingenio Blocks" />
        </Link>
        <Link to="/" className="co-volver">← Seguir comprando</Link>
      </div>
      <div className="co-titulo">
        <h1>{titulo}</h1>
        <span className="lp-underline" />
      </div>
    </div>
  )
}

export default function Checkout() {
  const location = useLocation()
  const { user } = useAuth()
  const product = location.state?.product

  // Solo el kit es físico y se despacha. El resto (packs de modelos, planes)
  // son digitales: el acceso llega al Aula Virtual, sin envío.
  const requiereEnvio = product ? !product.is_digital : false

  // Packs/planes solo para alumnos. El servidor lo revalida igual en
  // build_order_from_request; esto es para no mostrar un formulario que
  // terminaría rebotando al pagar.
  const bloqueadoPorLogin = product?.requires_login && !user

  // `student` (nombre del niño/a) es obligatorio: el diploma se emite a su nombre.
  const [contact, setContact] = useState({ name: '', student: '', email: '', phone: '' })
  const [tocado, setTocado] = useState({})   // campos que la persona ya visitó
  const [regions, setRegions] = useState([])
  const [region, setRegion] = useState('')
  const [commune, setCommune] = useState('')       // nombre (se muestra y se guarda)
  const [communeId, setCommuneId] = useState(null) // id de comuna de Shipit (para cotizar)
  const [address, setAddress] = useState({ street: '', number: '', detail: '' })
  const [quotes, setQuotes] = useState([])
  const [quoting, setQuoting] = useState(false)
  const [quoteMsg, setQuoteMsg] = useState('')
  const [courier, setCourier] = useState(null) // {courier, service, price, days}
  const [paying, setPaying] = useState(false)

  // Con sesión iniciada, el correo de la cuenta viene puesto. En los productos
  // "solo para alumnos" además queda fijo: el servidor ancla la compra a esa
  // cuenta, así que dejarlo editable solo confundiría.
  useEffect(() => {
    if (user?.email) setContact(c => (c.email ? c : { ...c, email: user.email }))
  }, [user])

  useEffect(() => {
    if (product && requiereEnvio) {
      api.get('/shipping/communes/')
        .then(res => setRegions(res.data.regions || []))
        .catch(() => {}) // sin comunas el formulario igual permite reintentar
    }
  }, [product, requiereEnvio])

  if (!product) {
    return (
      <div className="lp co-page">
        <Cabecera titulo="Finalizar compra" />
        <div className="co-aviso">
          <h2>No hay ningún producto seleccionado</h2>
          <p>Elige un kit o un plan para continuar con tu compra.</p>
          <div className="co-aviso-acciones">
            <Link to="/#kits" className="lp-btn-yellow lp-btn-cta">Ver los kits</Link>
          </div>
        </div>
      </div>
    )
  }

  if (bloqueadoPorLogin) {
    return (
      <div className="lp co-page">
        <Cabecera titulo="Solo para alumnos" />
        <div className="co-aviso">
          <h2>{product.name}</h2>
          <p>
            Este plan está disponible solo para quienes ya tienen cuenta de Ingenio
            Blocks. La cuenta se crea al comprar un kit con piezas, y te llega por
            correo apenas se aprueba el pago.
          </p>
          <p>Si ya compraste tu kit, inicia sesión con ese correo para continuar.</p>
          <div className="co-aviso-acciones">
            <Link
              to="/login"
              state={{ from: '/checkout', checkoutProduct: product }}
              className="lp-btn-yellow lp-btn-cta"
            >
              Iniciar sesión
            </Link>
            <Link to="/#kits" className="co-btn-cotizar">Ver los kits</Link>
          </div>
        </div>
      </div>
    )
  }

  const communesForRegion = regions.find(r => r.region === region)?.communes || []

  // El Combobox trabaja con {label, ...extra}: la región solo necesita el
  // nombre; la comuna arrastra su id de Shipit para poder cotizar.
  const opcionesRegion = regions.map(r => ({ label: r.region }))
  const opcionesComuna = communesForRegion.map(c => ({ label: c.name, id: c.id }))

  const handleQuote = () => {
    if (!commune) return
    setQuoting(true); setQuoteMsg(''); setQuotes([]); setCourier(null)
    api.post('/shipping/quote/', {
      product_ids: [product.id], commune_name: commune, commune_id: communeId,
    })
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

  // effective_price, NO price: es lo que realmente cobra el servidor
  // (payments/orders.py usa p.effective_price). Con `price` un producto en
  // oferta mostraba un total distinto al cobrado.
  const enOferta = product.is_on_sale && product.sale_price != null
  const precio = parseInt(product.effective_price ?? product.price, 10)
  const envio = courier ? courier.price : 0
  const total = precio + envio

  // Errores por campo. Se calculan siempre, pero solo se MUESTRAN cuando la
  // persona ya pasó por el campo (`tocado`) o cuando intentó pagar: mostrar
  // "falta el nombre" apenas abre el formulario es hostil.
  const errores = {
    name: errorNombre(contact.name, 'nombre del apoderado'),
    student: errorNombre(contact.student, 'nombre del niño o niña'),
    email: errorEmail(contact.email),
    phone: errorTelefono(contact.phone),
    ...(requiereEnvio ? {
      region: errorTexto(region, 'Elige tu región.'),
      commune: errorTexto(commune, 'Elige tu comuna.'),
      street: errorTexto(address.street, 'Falta la calle.'),
      number: errorTexto(address.number, 'Falta el número.'),
    } : {}),
  }
  const ver = (campo) => (tocado[campo] ? errores[campo] : '')

  const datosListos = !errores.name && !errores.student && !errores.email && !errores.phone
  const direccionLista = !requiereEnvio ||
    (!errores.region && !errores.commune && !errores.street && !errores.number)
  const entregaLista = direccionLista && (!requiereEnvio || courier)
  const puedePagar = datosListos && entregaLista && !paying

  const marcarTodo = () => setTocado(Object.fromEntries(Object.keys(errores).map(k => [k, true])))

  const handleCheckout = async (gateway) => {
    // Último resguardo: si igual se llama con datos malos, se marcan los
    // campos para que se vean los errores en vez de rebotar en el servidor.
    if (!puedePagar) { marcarTodo(); return }
    setPaying(true)
    const payload = {
      product_ids: [product.id],
      email: contact.email,
      customer_name: contact.name,
      student_name: contact.student,   // va al diploma
      phone: contact.phone,
    }
    if (requiereEnvio) {
      payload.shipping = {
        recipient_name: contact.name,
        recipient_phone: contact.phone,
        recipient_email: contact.email,
        region, commune, commune_id: communeId,
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
      setQuoteMsg('')
      alert(err.response?.data?.error || 'Error al iniciar el pago')
      setPaying(false)
    }
  }

  return (
    <div className="lp co-page">
      <Cabecera titulo="Finalizar compra" />

      <div className="co-body">
        {/* ---------- Formulario ---------- */}
        <div>
          <section className="co-card">
            <div className="co-paso-cabecera">
              <span className="co-paso-num">1</span>
              <h2>Tus datos</h2>
            </div>

            <div className="co-campo">
              <label htmlFor="co-nombre">Nombre del apoderado</label>
              <input id="co-nombre" placeholder="Nombre y apellido"
                className={ver('name') ? 'co-input-error' : undefined}
                value={contact.name}
                onBlur={() => setTocado(t => ({ ...t, name: true }))}
                onChange={e => setContact({ ...contact, name: e.target.value })} />
              {ver('name') && <p className="co-error">{ver('name')}</p>}
            </div>

            <div className="co-campo">
              <label htmlFor="co-alumno">Nombre del niño o niña</label>
              <input id="co-alumno" placeholder="Nombre y apellido del alumno"
                className={ver('student') ? 'co-input-error' : undefined}
                value={contact.student}
                onBlur={() => setTocado(t => ({ ...t, student: true }))}
                onChange={e => setContact({ ...contact, student: e.target.value })} />
              {ver('student')
                ? <p className="co-error">{ver('student')}</p>
                : <p className="co-ayuda">Así saldrá impreso en sus diplomas.</p>}
            </div>

            <div className="co-fila">
              <div className="co-campo">
                <label htmlFor="co-email">Email</label>
                <input id="co-email" type="email" placeholder="tu@correo.cl"
                  className={ver('email') ? 'co-input-error' : undefined}
                  readOnly={product.requires_login}
                  value={contact.email}
                  onBlur={() => setTocado(t => ({ ...t, email: true }))}
                  onChange={e => setContact({ ...contact, email: e.target.value })} />
                {ver('email')
                  ? <p className="co-error">{ver('email')}</p>
                  : <p className="co-ayuda">Acá llegará el acceso al Aula Virtual.</p>}
              </div>
              <div className="co-campo">
                <label htmlFor="co-fono">Teléfono</label>
                <input id="co-fono" placeholder="+56 9 1234 5678" inputMode="tel"
                  className={ver('phone') ? 'co-input-error' : undefined}
                  value={contact.phone}
                  onBlur={() => setTocado(t => ({ ...t, phone: true }))}
                  onChange={e => setContact({ ...contact, phone: e.target.value })} />
                {ver('phone') && <p className="co-error">{ver('phone')}</p>}
              </div>
            </div>

            {product.requires_login && (
              <p className="co-nota co-nota-ok">
                <span aria-hidden="true">🔒</span>
                Esta compra queda asociada a tu cuenta ({contact.email}).
              </p>
            )}
          </section>

          {/* Paso 2 solo si hay algo físico que despachar */}
          {requiereEnvio ? (
            <section className="co-card">
              <div className="co-paso-cabecera">
                <span className="co-paso-num">2</span>
                <h2>Dirección de envío</h2>
              </div>

              <div className="co-fila">
                <div className="co-campo">
                  <label htmlFor="co-region">Región</label>
                  <Combobox
                    id="co-region"
                    placeholder="Escribe o elige tu región"
                    options={opcionesRegion}
                    value={region}
                    onSelect={op => {
                      setRegion(op.label); setCommune(''); setCommuneId(null)
                      setQuotes([]); setCourier(null)
                      setTocado(t => ({ ...t, region: true }))
                    }}
                  />
                  {ver('region') && <p className="co-error">{ver('region')}</p>}
                </div>
                <div className="co-campo">
                  <label htmlFor="co-comuna">Comuna</label>
                  <Combobox
                    id="co-comuna"
                    placeholder={region ? 'Escribe tu comuna' : 'Elige primero la región'}
                    disabled={!region}
                    options={opcionesComuna}
                    value={commune}
                    onSelect={op => {
                      // la opción trae el id de Shipit además del nombre
                      setCommune(op.label); setCommuneId(op.id ?? null)
                      setQuotes([]); setCourier(null)
                      setTocado(t => ({ ...t, commune: true }))
                    }}
                  />
                  {ver('commune') && <p className="co-error">{ver('commune')}</p>}
                </div>
              </div>

              <div className="co-fila co-fila-dir">
                <div className="co-campo">
                  <label htmlFor="co-calle">Calle</label>
                  <input id="co-calle" placeholder="Av. Siempre Viva"
                    className={ver('street') ? 'co-input-error' : undefined}
                    value={address.street}
                    onBlur={() => setTocado(t => ({ ...t, street: true }))}
                    onChange={e => setAddress({ ...address, street: e.target.value })} />
                  {ver('street') && <p className="co-error">{ver('street')}</p>}
                </div>
                <div className="co-campo">
                  <label htmlFor="co-numero">Número</label>
                  <input id="co-numero" placeholder="742"
                    className={ver('number') ? 'co-input-error' : undefined}
                    value={address.number}
                    onBlur={() => setTocado(t => ({ ...t, number: true }))}
                    onChange={e => setAddress({ ...address, number: e.target.value })} />
                  {ver('number') && <p className="co-error">{ver('number')}</p>}
                </div>
              </div>

              <div className="co-campo">
                <label htmlFor="co-detalle">Depto / oficina / referencia <span style={{ fontWeight: 400, color: '#94a3b8' }}>(opcional)</span></label>
                <input id="co-detalle" placeholder="Depto 301, torre B"
                  value={address.detail}
                  onChange={e => setAddress({ ...address, detail: e.target.value })} />
              </div>

              <button className="co-btn-cotizar" onClick={handleQuote} disabled={!commune || quoting}>
                {quoting ? 'Cotizando…' : 'Cotizar envío'}
              </button>

              {quoteMsg && <p className="co-msg co-msg-error">{quoteMsg}</p>}

              {quotes.length > 0 && (
                <div className="co-cotizaciones">
                  {quotes.map(q => (
                    <label key={q.courier + q.service}
                      className={'co-cotizacion' + (courier === q ? ' activa' : '')}>
                      <input type="radio" name="courier"
                        checked={courier === q} onChange={() => setCourier(q)} />
                      <span>
                        <span className="co-cot-nombre">{q.courier} · {q.service}</span>
                        <span className="co-cot-dias">{q.days}</span>
                      </span>
                      <span className="co-cot-precio">{clp(q.price)}</span>
                    </label>
                  ))}
                </div>
              )}
            </section>
          ) : (
            <section className="co-card">
              <div className="co-paso-cabecera">
                <span className="co-paso-num">2</span>
                <h2>Entrega</h2>
              </div>
              <p className="co-nota co-nota-info">
                <span aria-hidden="true">💻</span>
                Este plan es digital: no requiere envío. El acceso se activa en tu
                Aula Virtual apenas se aprueba el pago y te avisamos por correo.
              </p>
            </section>
          )}
        </div>

        {/* ---------- Resumen ---------- */}
        <aside className="co-resumen">
          {product.landing_badge && <span className="co-badge">{product.landing_badge}</span>}
          <h2>Resumen</h2>
          <p className="co-resumen-sub">Revisa antes de pagar</p>

          <div className="co-item">
            <span className="co-item-nombre">{product.name}</span>
            <span>
              {enOferta && <span className="co-item-antes">{clp(product.price)}</span>}
              <span className={enOferta ? 'co-item-oferta' : undefined}>{clp(precio)}</span>
            </span>
          </div>

          {requiereEnvio && (
            <div className="co-item">
              <span>Envío {courier ? `(${courier.courier})` : ''}</span>
              <span>{courier ? clp(envio) : '—'}</span>
            </div>
          )}

          <div className="co-total">
            <span>Total</span>
            <span>{clp(total)}</span>
          </div>
          {product.price_note && (
            <p className="co-resumen-sub" style={{ margin: '2px 0 0', textAlign: 'right' }}>
              {product.price_note}
            </p>
          )}

          <div className="co-pagos">
            <button className="co-btn-pagar co-btn-webpay"
              disabled={!puedePagar} onClick={() => handleCheckout('webpay')}>
              Pagar con Webpay
            </button>
            <button className="co-btn-pagar co-btn-mp"
              disabled={!puedePagar} onClick={() => handleCheckout('mercadopago')}>
              Pagar con MercadoPago
            </button>
          </div>

          {!puedePagar && !paying && (
            <p className="co-hint">
              {!datosListos
                ? 'Completa tus datos para continuar'
                : !direccionLista
                  ? 'Completa la dirección de envío'
                  : 'Cotiza el envío y elige un courier'}
            </p>
          )}
          {paying && <p className="co-hint">Redirigiendo al pago…</p>}

          <p className="co-seguro">
            <span aria-hidden="true">🔒</span> Pago seguro · Webpay y MercadoPago
          </p>
        </aside>
      </div>
    </div>
  )
}
