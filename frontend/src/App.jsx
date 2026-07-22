import { useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import './App.css'
import Landing from './pages/Landing'
import Catalog from './pages/Catalog'
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

function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/tienda" element={<Catalog />} />
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
      <ScrollTopButton />
      <WhatsAppButton />
    </>
  )
}

export default App
