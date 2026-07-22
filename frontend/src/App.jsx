import { useEffect } from 'react'
import { Routes, Route, useLocation, Navigate } from 'react-router-dom'
import './App.css'
import Landing from './pages/Landing'
import Checkout from './pages/Checkout'
import CheckoutSuccess from './pages/CheckoutSuccess'
import CheckoutFailed from './pages/CheckoutFailed'
import Login from './pages/Login'
import SetPassword from './pages/SetPassword'
import MyCourses from './pages/MyCourses'
import Profile from './pages/Profile'
import CourseView from './pages/CourseView'
import NotFound from './pages/NotFound'
import RequireAuth from './components/RequireAuth'
import ScrollTopButton from './components/ScrollTopButton'
import WhatsAppButton from './components/WhatsAppButton'

// Al cambiar de ruta la página nueva parte arriba (sin animar el salto,
// para no interferir con el scroll suave de las anclas de la landing).
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [pathname])
  return null
}

// Rutas donde los botones flotantes estorban en vez de ayudar: en el checkout
// se paran justo encima del botón de pagar cuando el resumen cae al final en
// móvil, y en el login (diseñado para no tener scroll) se montan sobre la
// tarjeta en pantallas bajas.
const SIN_BOTONES_FLOTANTES = ['/checkout', '/login', '/definir-clave', '/curso']

function BotonesFlotantes() {
  const { pathname } = useLocation()
  const oculto = SIN_BOTONES_FLOTANTES.some(
    (ruta) => pathname === ruta || pathname.startsWith(`${ruta}/`)
  )
  if (oculto) return null
  return (
    <>
      <ScrollTopButton />
      <WhatsAppButton />
    </>
  )
}

function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/" element={<Landing />} />
      {/* /tienda era el catálogo del prototipo anterior: gris, sin el sistema
          visual de la marca y sin footer. Ya no se enlaza desde ninguna parte,
          pero la ruta se mantiene redirigiendo para que un marcador o un link
          antiguo no caiga en una página que parece de otro producto. */}
      <Route path="/tienda" element={<Navigate to="/#kits" replace />} />
      <Route path="/checkout" element={<Checkout />} />
      <Route path="/checkout/success" element={<CheckoutSuccess />} />
      <Route path="/checkout/failed" element={<CheckoutFailed />} />

      {/* Auth */}
      <Route path="/login" element={<Login />} />
      <Route path="/definir-clave/:uid/:token" element={<SetPassword />} />

      {/* LMS alumno */}
      <Route path="/mis-cursos" element={<RequireAuth><MyCourses /></RequireAuth>} />
      <Route path="/mi-cuenta" element={<RequireAuth><Profile /></RequireAuth>} />
      <Route path="/curso/:slug" element={<RequireAuth><CourseView /></RequireAuth>} />

      {/* Comodín: cualquier ruta desconocida. Va al final para no tapar las de
          arriba. En producción nginx entrega index.html en todas las rutas, así
          que este es el único 404 que ve el visitante del sitio público. */}
      <Route path="*" element={<NotFound />} />
      </Routes>
      <BotonesFlotantes />
    </>
  )
}

export default App
