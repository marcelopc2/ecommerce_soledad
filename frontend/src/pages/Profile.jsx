import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import './lms.css'
import './profile.css'
import CampoClave from '../components/CampoClave'
import Cargando from '../components/Cargando'

/* Mismas reglas que el checkout y que el servidor (payments/serializers.py). */
function errorNombre(v, que, obligatorio = true) {
  const t = (v || '').trim()
  if (!t) return obligatorio ? `Falta el ${que}.` : ''
  if (t.length < 2) return `Escribe el ${que} completo.`
  if (/\d/.test(t)) return `El ${que} no puede tener números.`
  return ''
}

export default function Profile() {
  const { refreshMe } = useAuth()
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [form, setForm] = useState({ student_name: '', parent_name: '' })
  const [tocado, setTocado] = useState({})
  const [guardando, setGuardando] = useState(false)
  const [aviso, setAviso] = useState('')       // mensaje de éxito
  const [errorApi, setErrorApi] = useState('')

  // Foto de perfil
  const [subiendo, setSubiendo] = useState(false)
  const [errorFoto, setErrorFoto] = useState('')

  // Cambio de contraseña (endpoint aparte: pide la actual)
  const [claves, setClaves] = useState({ actual: '', nueva: '', repetir: '' })
  const [cambiando, setCambiando] = useState(false)
  const [avisoClave, setAvisoClave] = useState('')
  const [errorClave, setErrorClave] = useState('')

  useEffect(() => {
    api.get('/auth/profile/')
      .then(r => {
        setDatos(r.data)
        setForm({
          student_name: r.data.student_name || '',
          parent_name: r.data.parent_name || '',
        })
      })
      .catch(() => setErrorApi('No pudimos cargar tu perfil. Recarga la página.'))
      .finally(() => setCargando(false))
  }, [])

  if (cargando) {
    return <div className="lms"><LmsHeader /><LmsLoader text="Cargando tu perfil…" /></div>
  }

  const errores = {
    student_name: errorNombre(form.student_name, 'nombre del niño o niña'),
    parent_name: errorNombre(form.parent_name, 'nombre del apoderado', false),
  }
  const ver = (c) => (tocado[c] ? errores[c] : '')
  const hayErrores = Object.values(errores).some(Boolean)

  const sinCambios = datos &&
    form.student_name === (datos.student_name || '') &&
    form.parent_name === (datos.parent_name || '')

  const guardar = (e) => {
    e.preventDefault()
    setTocado({ student_name: true, parent_name: true })
    if (hayErrores) return
    setGuardando(true); setAviso(''); setErrorApi('')
    api.patch('/auth/profile/', form)
      .then(r => {
        setDatos(r.data)
        setAviso('Listo, guardamos los cambios.')
      })
      .catch(err => {
        const d = err.response?.data
        // DRF devuelve {campo: [mensaje]}; se muestra el primero.
        const msg = d?.error || (d && Object.values(d)[0]?.[0]) || 'No pudimos guardar los cambios.'
        setErrorApi(msg)
      })
      .finally(() => setGuardando(false))
  }

  // El avatar sale también en el encabezado de todas las pantallas del Aula, y
  // ese dato lo tiene el contexto de sesión: sin refreshMe() la foto cambiaría
  // acá pero el chip de arriba seguiría con la vieja hasta recargar.
  const subirFoto = (e) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''            // permite volver a elegir el mismo archivo
    if (!archivo) return
    setErrorFoto(''); setSubiendo(true)
    const fd = new FormData()
    fd.append('avatar', archivo)
    api.patch('/auth/profile/', fd)
      .then(r => { setDatos(r.data); return refreshMe() })
      .catch(err => setErrorFoto(err.response?.data?.error || 'No pudimos subir la foto.'))
      .finally(() => setSubiendo(false))
  }

  const quitarFoto = () => {
    setErrorFoto(''); setSubiendo(true)
    api.delete('/auth/profile/')
      .then(r => { setDatos(r.data); return refreshMe() })
      .catch(() => setErrorFoto('No pudimos quitar la foto.'))
      .finally(() => setSubiendo(false))
  }

  const cambiarClave = (e) => {
    e.preventDefault()
    setAvisoClave(''); setErrorClave('')
    if (claves.nueva !== claves.repetir) {
      setErrorClave('Las contraseñas nuevas no coinciden.')
      return
    }
    setCambiando(true)
    api.post('/auth/change-password/', {
      current_password: claves.actual,
      new_password: claves.nueva,
    })
      .then(() => {
        setAvisoClave('Tu contraseña quedó actualizada.')
        setClaves({ actual: '', nueva: '', repetir: '' })
      })
      .catch(err => setErrorClave(err.response?.data?.error || 'No pudimos cambiar la contraseña.'))
      .finally(() => setCambiando(false))
  }

  const vence = datos?.membership?.expires_at
    ? new Date(datos.membership.expires_at).toLocaleDateString('es-CL')
    : null

  return (
    <div className="lms">
      <LmsHeader />

      <section className="lms-hero">
        <div className="deco d1" /><div className="deco d2" /><div className="deco d3" />
        <div className="lms-hero-inner">
          <h1>Mi cuenta</h1>
          <p>Revisa y corrige los datos de tu cuenta.</p>
        </div>
      </section>

      {/* Dos columnas, igual que Mi cuenta del panel: a la izquierda lo que se
          edita seguido (foto y nombres), a la derecha lo que se toca de vez en
          cuando. En una sola columna la contraseña quedaba tan abajo que había
          que buscarla. Bajo 900px se apilan solas. */}
      <div className="pf-body">
        <div className="pf-col">
        {/* ---------- Foto y datos ---------- */}
        <form className="pf-card" onSubmit={guardar}>
          <h2>Tus datos</h2>
          <div className="pf-avatar-fila">
            {datos?.avatar_url
              ? <img src={datos.avatar_url} alt="" className="pf-avatar" />
              : <span className="pf-avatar pf-avatar-inicial">
                  {(datos?.email || '?')[0].toUpperCase()}
                </span>}
            <div className="pf-avatar-acciones">
              <label className="pf-btn pf-btn-file">
                {subiendo ? 'Subiendo…' : 'Cambiar foto'}
                <input type="file" accept="image/jpeg,image/png,image/webp"
                       onChange={subirFoto} disabled={subiendo} hidden />
              </label>
              {datos?.avatar_url && (
                <button type="button" className="pf-link-btn" onClick={quitarFoto} disabled={subiendo}>
                  Quitar foto
                </button>
              )}
              <p className="pf-ayuda">JPG, PNG o WEBP. Cuadrada se ve mejor.</p>
              {errorFoto && <p className="pf-msg pf-msg-error">{errorFoto}</p>}
            </div>
          </div>

          <hr className="pf-sep" />

          <div className="pf-campo">
            <label htmlFor="pf-alumno">Nombre del niño o niña</label>
            <input
              id="pf-alumno"
              className={ver('student_name') ? 'pf-error-input' : undefined}
              value={form.student_name}
              onBlur={() => setTocado(t => ({ ...t, student_name: true }))}
              onChange={e => { setForm({ ...form, student_name: e.target.value }); setAviso('') }}
            />
            {ver('student_name')
              ? <p className="pf-error">{ver('student_name')}</p>
              : <p className="pf-ayuda">Así saldrá impreso en sus diplomas. Si lo corriges,
                  los diplomas que ya obtuvo también salen con el nombre nuevo.</p>}
          </div>

          <div className="pf-campo">
            <label htmlFor="pf-apoderado">Nombre del apoderado</label>
            <input
              id="pf-apoderado"
              className={ver('parent_name') ? 'pf-error-input' : undefined}
              value={form.parent_name}
              onBlur={() => setTocado(t => ({ ...t, parent_name: true }))}
              onChange={e => { setForm({ ...form, parent_name: e.target.value }); setAviso('') }}
            />
            {ver('parent_name') && <p className="pf-error">{ver('parent_name')}</p>}
          </div>

          <div className="pf-campo">
            <label htmlFor="pf-email">Correo de la cuenta</label>
            <input id="pf-email" value={datos?.email || ''} readOnly />
            <p className="pf-ayuda">
              Con este correo entras al Aula Virtual. Si necesitas cambiarlo,
              escríbenos a contacto@ingenioblocks.com.
            </p>
          </div>

          {errorApi && <p className="pf-msg pf-msg-error">{errorApi}</p>}
          {aviso && <p className="pf-msg pf-msg-ok">{aviso}</p>}

          <button className="pf-btn" type="submit" disabled={guardando || sinCambios || hayErrores}>
            {guardando ? <><Cargando />Guardando…</> : 'Guardar cambios'}
          </button>
        </form>
        </div>

        <div className="pf-col">
        {/* ---------- Membresía ---------- */}
        <div className="pf-card pf-card-sec">
          <h2>Tu acceso</h2>
          {datos?.membership ? (
            <>
              <p className={'pf-estado ' + (datos.membership.active ? 'ok' : 'vencido')}>
                {datos.membership.active ? 'Activo' : 'Vencido'}
              </p>
              {vence && (
                <p className="pf-ayuda">
                  {datos.membership.active ? 'Vigente hasta el ' : 'Venció el '}{vence}.
                </p>
              )}
              <Link to="/mis-cursos" className="pf-link">Ir a mis cursos →</Link>
            </>
          ) : (
            <>
              <p className="pf-ayuda">Todavía no tienes una membresía activa.</p>
              <Link to="/#kits" className="pf-link">Ver los kits →</Link>
            </>
          )}
        </div>

        {/* ---------- Contraseña ---------- */}
        <form className="pf-card pf-card-sec" onSubmit={cambiarClave}>
          <h2>Cambiar contraseña</h2>

          <div className="pf-campo">
            <label htmlFor="pf-actual">Contraseña actual</label>
            <CampoClave id="pf-actual" value={claves.actual}
              onChange={e => setClaves({ ...claves, actual: e.target.value })} />
          </div>
          <div className="pf-campo">
            <label htmlFor="pf-nueva">Contraseña nueva</label>
            <CampoClave id="pf-nueva" value={claves.nueva}
              onChange={e => setClaves({ ...claves, nueva: e.target.value })} />
          </div>
          <div className="pf-campo">
            <label htmlFor="pf-repetir">Repite la contraseña nueva</label>
            <CampoClave id="pf-repetir" value={claves.repetir}
              onChange={e => setClaves({ ...claves, repetir: e.target.value })} />
          </div>

          {errorClave && <p className="pf-msg pf-msg-error">{errorClave}</p>}
          {avisoClave && <p className="pf-msg pf-msg-ok">{avisoClave}</p>}

          <button className="pf-btn" type="submit"
            disabled={cambiando || !claves.actual || !claves.nueva || !claves.repetir}>
            {cambiando ? 'Cambiando…' : 'Cambiar contraseña'}
          </button>
        </form>
        </div>
      </div>
    </div>
  )
}
