import { Routes, Route } from 'react-router-dom'
import './App.css'
import Landing from './pages/Landing'
import Catalog from './pages/Catalog'
import Checkout from './pages/Checkout'
import CheckoutSuccess from './pages/CheckoutSuccess'
import CheckoutFailed from './pages/CheckoutFailed'
import Login from './pages/Login'
import SetPassword from './pages/SetPassword'
import MyCourses from './pages/MyCourses'
import CourseView from './pages/CourseView'
import Panel from './pages/panel/Panel'
import RequireAuth from './components/RequireAuth'

function App() {
  return (
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
      <Route path="/curso/:slug" element={<RequireAuth><CourseView /></RequireAuth>} />

      {/* Panel CMS de la clienta (solo staff) */}
      <Route path="/panel/*" element={<RequireAuth staffOnly><Panel /></RequireAuth>} />
    </Routes>
  )
}

export default App
