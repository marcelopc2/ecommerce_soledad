import { useParams, Link, Navigate } from 'react-router-dom'
import { LandingFooter } from '../components/LandingSections'
import logo from '../assets/landing/logo-ingenioblocks.svg'
import './landing.css'
import './legal.css'

/*
  Documentos legales. El CONTENIDO son borradores razonables para el rubro
  (venta a distancia en Chile, a familias, con datos de menores), pero NO son
  asesoría jurídica: deben pasar por alguien que sepa de derecho antes de
  publicarse, y hay que completar los datos de la empresa marcados con [ ].

  Se sirven como página propia (no un PDF) para que se puedan corregir sin
  volver a subir un archivo, y para que el buscador los indexe.
*/

const ACTUALIZADO = 'julio de 2026'

const DOCS = {
  terminos: {
    titulo: 'Términos y condiciones',
    bloques: [
      ['1. Quiénes somos',
       'Ingenio Blocks ([razón social], RUT [ ], domicilio en [ ], Chile) vende ' +
       'kits de bloques educativos y acceso a un aula virtual con contenido para ' +
       'niños y niñas desde los 6 años. Para contactarnos: contacto@ingenioblocks.com.'],
      ['2. Qué se vende',
       'El kit físico incluye las piezas y se despacha a domicilio. Los planes y ' +
       'packs de modelos son productos digitales: dan acceso al aula virtual, donde ' +
       'se libera un modelo nuevo por semana. El acceso digital no se despacha; se ' +
       'habilita en la cuenta del comprador.'],
      ['3. Cuenta y acceso',
       'Al comprar un kit se crea una cuenta con el correo indicado en la compra. ' +
       'Desde ahí se define una contraseña para entrar al aula virtual. La cuenta es ' +
       'personal: no debe compartirse ni revenderse el contenido. Los planes y ' +
       'modelos adicionales solo pueden comprarse con la sesión iniciada.'],
      ['4. Precios y pago',
       'Los precios están en pesos chilenos e incluyen IVA. El pago se procesa a ' +
       'través de Webpay (Transbank) o MercadoPago; Ingenio Blocks no almacena los ' +
       'datos de la tarjeta. El costo de despacho se calcula al momento de la compra ' +
       'según la comuna de destino. Por cada compra se emite boleta electrónica.'],
      ['5. Despacho',
       'El kit físico se despacha a través del courier elegido en el checkout, a la ' +
       'dirección indicada. Los plazos son estimados del courier y pueden variar. El ' +
       'seguimiento se envía por correo una vez despachado el pedido.'],
      ['6. Uso del contenido',
       'El contenido del aula virtual (videos, instrucciones, imágenes) es de ' +
       'Ingenio Blocks y se entrega solo para uso personal del alumno. No está ' +
       'permitido descargarlo para redistribuirlo, publicarlo ni usarlo con fines ' +
       'comerciales.'],
      ['7. Contacto y reclamos',
       'Cualquier consulta, reclamo o solicitud puede dirigirse a ' +
       'contacto@ingenioblocks.com. Respondemos dentro de los plazos que exige la ' +
       'ley del consumidor.'],
    ],
  },

  privacidad: {
    titulo: 'Política de privacidad',
    bloques: [
      ['1. Qué datos pedimos',
       'Para procesar una compra pedimos: nombre del apoderado, correo, teléfono, ' +
       'y —cuando hay despacho— la dirección. Pedimos también el NOMBRE DEL NIÑO O ' +
       'NIÑA, únicamente para emitir a su nombre el diploma de la actividad. No ' +
       'pedimos ningún otro dato del menor.'],
      ['2. Para qué los usamos',
       'Los datos se usan para: procesar el pago y emitir la boleta, coordinar el ' +
       'despacho, dar acceso al aula virtual, emitir el diploma a nombre del niño o ' +
       'niña, y enviar los correos propios del servicio (bienvenida, aviso de ' +
       'modelo nuevo, diploma). No los usamos para publicidad de terceros ni los ' +
       'vendemos.'],
      ['3. Con quién se comparten',
       'Solo con los proveedores necesarios para completar la compra: la pasarela ' +
       'de pago (Transbank / MercadoPago), el emisor de boletas (OpenFactura) y el ' +
       'courier de despacho (a través de Shipit). Cada uno recibe únicamente lo ' +
       'necesario para su parte.'],
      ['4. Datos de menores de edad',
       'El único dato de un menor que tratamos es su nombre de pila, para el ' +
       'diploma, y lo entrega su apoderado al comprar. El apoderado puede corregirlo ' +
       'o pedir su eliminación en cualquier momento escribiéndonos.'],
      ['5. Tus derechos',
       'Puedes pedir acceder, corregir o eliminar tus datos (y los del menor a tu ' +
       'cargo) escribiendo a contacto@ingenioblocks.com. El nombre del niño o niña ' +
       'también se puede editar desde el perfil de la cuenta.'],
      ['6. Seguridad',
       'Las contraseñas se guardan cifradas y el pago se procesa en la pasarela, ' +
       'sin que Ingenio Blocks vea los datos de la tarjeta. El sitio funciona sobre ' +
       'conexión segura (HTTPS).'],
    ],
  },

  retracto: {
    titulo: 'Derecho a retracto y devoluciones',
    bloques: [
      ['Derecho a retracto (10 días)',
       'Según la Ley del Consumidor, en las compras a distancia tienes derecho a ' +
       'retractarte dentro de los 10 días corridos siguientes a la recepción del ' +
       'producto, siempre que no lo hayas usado y esté en las mismas condiciones en ' +
       'que lo recibiste. Para ejercerlo, escríbenos a contacto@ingenioblocks.com ' +
       'indicando tu número de pedido.'],
      ['Kit físico',
       'Si retractas la compra del kit, coordinamos la devolución del producto y te ' +
       'reembolsamos lo pagado, incluido el despacho de ida, según lo que establece ' +
       'la ley. El costo de la devolución se acuerda en cada caso.'],
      ['Contenido digital',
       'El acceso al aula virtual es contenido digital: si ya se activó y se empezó ' +
       'a usar, el retracto puede no aplicar, tal como permite la ley para este tipo ' +
       'de productos. Si compraste un plan digital y no lo has usado, escríbenos y ' +
       'lo revisamos.'],
      ['Producto con falla',
       'Si el kit llega con alguna pieza defectuosa o incompleta, contáctanos: lo ' +
       'reponemos o reembolsamos según corresponda. Esto es independiente del plazo ' +
       'de retracto.'],
      ['Cómo pedirlo',
       'Escribe a contacto@ingenioblocks.com con tu número de pedido y el motivo. ' +
       'Te respondemos con los pasos a seguir dentro de los plazos legales.'],
    ],
  },
}

export default function Legal() {
  const { doc } = useParams()
  const contenido = DOCS[doc]
  if (!contenido) return <Navigate to="/legal/terminos" replace />

  return (
    <div className="lp">
      <div className="legal-page">
        <div className="legal-top">
          <div className="legal-top-inner">
            <Link to="/" className="legal-logo"><img src={logo} alt="Ingenio Blocks" /></Link>
          </div>
        </div>

        <div className="legal-wrap">
          <nav className="legal-tabs">
            <Link to="/legal/terminos" className={doc === 'terminos' ? 'activo' : undefined}>Términos y condiciones</Link>
            <Link to="/legal/privacidad" className={doc === 'privacidad' ? 'activo' : undefined}>Privacidad</Link>
            <Link to="/legal/retracto" className={doc === 'retracto' ? 'activo' : undefined}>Retracto y devoluciones</Link>
          </nav>

          <article className="legal-doc">
            <h1>{contenido.titulo}</h1>
            <p className="legal-fecha">Última actualización: {ACTUALIZADO}</p>
            {contenido.bloques.map(([titulo, texto]) => (
              <section key={titulo}>
                <h2>{titulo}</h2>
                <p>{texto}</p>
              </section>
            ))}
          </article>
        </div>

        <LandingFooter />
      </div>
    </div>
  )
}
