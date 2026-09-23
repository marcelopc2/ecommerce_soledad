import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api, PANEL_URL } from '../api'
import LmsHeader, { LmsLoader } from '../components/LmsHeader'
import { openDiploma } from '../lib/diploma'
import './lms.css'
import Cargando from '../components/Cargando'

export default function MyCourses() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  // Un minuto basta para decidir en que estado va cada modelo: el goteo
  // libera por dia. El segundero del contador corre aparte, en su tarjeta.
  const ahora = useAhora(60000)

  // useCallback y no una función suelta: `cargar` viaja a las 44 tarjetas como
  // `onReady`. Si cambia de identidad en cada repintado, el efecto que programa
  // la apertura automática se desarma y se rearma en todas, cada vez.
  const cargar = useCallback(() => {
    setLoading(true)
    setError(false)
    api.get('/lms/my-courses/')
      .then(r => setData(r.data))
      // Un fallo de red NO es lo mismo que "no tienes cursos": antes los dos
      // se veían igual y un corte de conexión se leía como "perdí mi compra".
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { cargar() }, [cargar])

  if (loading) {
    return <div className="lms"><LmsHeader /><LmsLoader text="Cargando tus cursos…" /></div>
  }

  if (error) {
    return (
      <div className="lms">
        <LmsHeader />
        <div className="lms-content">
          <div className="lms-empty">
            <span className="big" aria-hidden="true">⚠️</span>
            <h3>No pudimos cargar tus cursos</h3>
            <p>
              Puede ser un problema de conexión. Tu compra y tu avance están a
              salvo: vuelve a intentarlo en un momento.
            </p>
            <button className="lms-btn yellow" onClick={cargar}>Reintentar</button>
          </div>
        </div>
      </div>
    )
  }

  const membership = data.membership
  // Cuenta de gestión mirando el Aula sin ser alumna: ve todo el contenido
  // desbloqueado. No hay membresía, así que se fuerza `active` para que las
  // tarjetas no se muestren como "membresía vencida".
  const preview = data.preview === true
  const active = preview ? true : membership?.active
  const expires = membership?.expires_at
    ? new Date(membership.expires_at).toLocaleDateString('es-CL')
    : null
  const items = data.items || []

  return (
    <div className="lms">
      <LmsHeader />

      <section className="lms-hero">
        <div className="deco d1" /><div className="deco d2" /><div className="deco d3" />
        <div className="lms-hero-inner">
          <div>
            <h1>{preview ? 'Vista previa del Aula' : 'Mi academia'}</h1>
            <p className="sub">
              {preview
                ? 'Así ve el Aula un alumno. Todo desbloqueado, sin guardar avance.'
                : active
                  ? 'Tu ruta de aprendizaje, paso a paso.'
                  /* Con la suscripción caída lo primero que hay que aclarar es
                     que no perdió nada: lo terminado sigue ahí. */
                  : 'Puedes volver a ver los modelos que terminaste. Renueva para seguir avanzando.'}
            </p>
          </div>
          <div className="lms-hero-right">
            {preview && (
              <span className="lms-mem-chip preview">👁 Cuenta de gestión</span>
            )}
            {membership && (
              active
                ? <span className="lms-mem-chip ok">✓ Membresía activa hasta el {expires}</span>
                : <>
                    <span className="lms-mem-chip bad">✕ Membresía vencida el {expires}</span>
                    <Link to="/#kits" className="lms-btn yellow">Renovar</Link>
                  </>
            )}
          </div>
        </div>
      </section>

      <div className="lms-content">
        {items.length === 0 ? (
          /* Dos situaciones muy distintas que antes mostraban el mismo texto:
             a alguien que acababa de pagar se le decía "compra un kit", que es
             lo peor que puede leer. Se distingue por si tiene membresía. */
          preview ? (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🧱</span>
              <h3>Todavía no hay cursos publicados</h3>
              <p>
                Cuando crees un curso en el panel aparecerá acá, tal como lo
                verá el alumno.
              </p>
              <a href={PANEL_URL} className="lms-btn yellow">Ir al panel</a>
            </div>
          ) : membership ? (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🎉</span>
              <h3>¡Tu acceso está activo!</h3>
              <p>
                Estamos preparando tu primer modelo. Te avisamos por correo
                apenas esté disponible: no tienes que hacer nada más.
              </p>
            </div>
          ) : (
            <div className="lms-empty">
              <span className="big" aria-hidden="true">🧱</span>
              <h3>Aún no tienes cursos</h3>
              <p>Al comprar un kit, su contenido aparece aquí automáticamente.</p>
              <Link to="/#kits" className="lms-btn yellow">Ver los kits</Link>
            </div>
          )
        ) : (
          <div className="lms-courses-grid">
            {/* El próximo por LLEGAR: el primero cuya fecha todavía no se
                cumple. Es el único que lleva contador, porque es la única
                espera real. Ojo que no es lo mismo que "el primero cerrado":
                un alumno atrasado arrastra modelos cuya fecha ya pasó y que
                solo esperan que termine el anterior. */}
            {(() => {
              const proximo = items.find(it => it.type !== 'diploma' && !it.unlocked
                && new Date(`${it.unlock_date}T00:00:00`).getTime() > ahora)
              return items.map(it => it.type === 'diploma'
                ? <DiplomaCard key={`d${it.id}`} diploma={it} />
                : <CourseCard key={`c${it.id}`} course={it} active={active}
                              onReady={cargar} esElProximo={it === proximo}
                              ahora={ahora} />
              )
            })()}
          </div>
        )}
      </div>
    </div>
  )
}

// El reloj vive en estado y no en un `Date.now()` suelto dentro del render.
// Leer la hora mientras se pinta hace que dos repintados del mismo estado den
// resultados distintos; ademas React lo marca como impuro. Asi el momento es
// un valor fijo durante todo el repintado, igual para todas las tarjetas.
//
// `intervaloMs` en 0 apaga el reloj: solo la tarjeta del proximo modelo
// necesita segundero, y poner 44 relojes latiendo seria repintar la pantalla
// entera cada segundo para que nadie lo note.
function useAhora(intervaloMs) {
  const [ahora, setAhora] = useState(Date.now)
  useEffect(() => {
    if (!intervaloMs) return
    const id = setInterval(() => setAhora(Date.now()), intervaloMs)
    return () => clearInterval(id)
  }, [intervaloMs])
  return ahora
}

// Cuánto falta para que se abra, en lenguaje natural. El goteo compara fechas en
// hora de Chile y libera a las 00:00, así que el objetivo es la medianoche local
// de unlock_date (para un usuario en Chile, su medianoche = la del servidor).
function faltaTexto(unlockDate, ahora) {
  const objetivo = new Date(`${unlockDate}T00:00:00`).getTime()
  const diff = objetivo - ahora
  if (diff <= 0) return 'hoy'
  const dias = Math.floor(diff / 86400000)
  if (dias >= 2) return `en ${dias} días`
  if (dias === 1) return 'mañana'
  const horas = Math.floor(diff / 3600000)
  if (horas >= 1) return `en ${horas} h`
  return `en ${Math.max(1, Math.floor(diff / 60000))} min`
}

// Cuenta regresiva que se ve moverse: "6 días y 4 h", "5 h 23 min", "48 s".
// Baja de unidad a medida que se acerca, para que el último rato sea el que
// más emociona.
function cuentaRegresiva(unlockDate, ahora) {
  const falta = new Date(`${unlockDate}T00:00:00`).getTime() - ahora
  if (falta <= 0) return '¡Ya se abrió!'
  const seg = Math.floor(falta / 1000)
  const d = Math.floor(seg / 86400)
  const h = Math.floor((seg % 86400) / 3600)
  const m = Math.floor((seg % 3600) / 60)
  if (d >= 1) return `Faltan ${d} ${d === 1 ? 'día' : 'días'} y ${h} h`
  if (h >= 1) return `Faltan ${h} h ${m} min`
  if (m >= 1) return `Faltan ${m} min ${seg % 60} s`
  return `¡Faltan ${seg} s!`
}

// "lunes 30 de septiembre". Una fecha concreta al lado del contador: "en 7
// días" sirve para hacerse una idea, pero el apoderado que quiere anotarlo en
// el calendario necesita el día.
function fechaEnPalabras(unlockDate) {
  return new Date(`${unlockDate}T00:00:00`).toLocaleDateString('es-CL', {
    weekday: 'long', day: 'numeric', month: 'long',
  })
}

function CourseCard({ course: c, active, onReady, esElProximo, ahora }) {
  // TRES ESTADOS, y el que manda es la FECHA del goteo:
  //
  //   abierto     la fecha llegó y terminó el anterior -> a todo color, se entra
  //   porTerminar la fecha llegó pero le falta el anterior -> a color, con candado
  //   esperando   la fecha todavía no llega -> apagado, con su animación
  //
  // Se decide por fecha y no por `lock_reason` porque un modelo puede tener las
  // dos trabas a la vez, y lo que el niño ve primero tiene que ser una sola
  // cosa: o "todavía no te toca" o "te toca, termina el anterior".
  // El segundero corre SOLO en el proximo por llegar; las demas se conforman
  // con el reloj de un minuto que baja del padre.
  const tic = useAhora(esElProximo ? 1000 : 0)
  const momento = esElProximo ? tic : ahora

  const vencido = c.lock_reason === 'vencida'
  const abierto = c.unlocked
  const fechaLlegada = new Date(`${c.unlock_date}T00:00:00`).getTime() <= momento
  const porTerminar = !abierto && !vencido && fechaLlegada
  const esperando = !abierto && !vencido && !fechaLlegada


  // Cuando llega la hora exacta, recargar para que el modelo se abra solo sin
  // que el niño tenga que refrescar.
  //
  // SOLO en el próximo por llegar, y solo si la espera cabe en un setTimeout.
  // El techo son 2.147.483.647 ms (~24,8 días) y pasarse NO lo posterga: lo
  // dispara de inmediato. Programándolo en los 20 modelos con fecha futura, el
  // que abría en julio de 2027 recargaba al instante, se volvía a montar y
  // recargaba otra vez: la página quedaba parpadeando entre "cargando" y la
  // lista. Más allá de ese plazo nadie deja la pestaña abierta, y si la deja,
  // el modelo aparece al siguiente refresco igual.
  useEffect(() => {
    if (!esElProximo || !esperando) return
    const falta = new Date(`${c.unlock_date}T00:00:00`).getTime() - Date.now()
    if (falta <= 0 || falta > 2147483647) return   // dentro del efecto sí se puede leer la hora
    const id = setTimeout(() => onReady?.(), falta + 1000)
    return () => clearTimeout(id)
  }, [esElProximo, esperando, c.unlock_date, onReady])

  const cuerpo = (
    <>
      <div className={'lms-course-cover' + (esperando ? ' velada' : '')}>
        {c.image_url
          ? <img src={c.image_url} alt={c.title} />
          : <span className="fallback">🧱</span>}

        {/* Se ganó la fecha pero le falta el anterior: la portada va a todo
            color -ya le corresponde- y el candado encima explica por qué no
            entra todavía. Sin contador: no hay nada que esperar, depende de él. */}
        {porTerminar && (
          <div className="lms-candado">
            <span className="lms-candado-ico" aria-hidden="true">🔒</span>
            <span className="lms-candado-txt">
              Termina {c.required_course_title
                ? `«${c.required_course_title}»` : 'el modelo anterior'}
            </span>
          </div>
        )}

        {c.completed ? (
          <span className="lock-badge done">✓ Completado</span>
        ) : vencido ? (
          <span className="lock-badge">🔒 Membresía vencida</span>
        ) : esperando ? (
          <span className="lock-badge">🔒 Se abre {faltaTexto(c.unlock_date, momento)}</span>
        ) : null}
      </div>

      <div className="lms-course-body">
        <h3>{c.title}</h3>
        <p>{c.description}</p>

        {/* El contador va SOLO en el próximo por llegar: es la única espera que
            le sirve de algo. En los de más atrás serían fechas cada vez más
            lejanas, y cuarenta relojes no emocionan a nadie. */}
        {esElProximo && esperando && (
          <p className="lms-que-sigue">
            <span className="cuenta">{cuentaRegresiva(c.unlock_date, momento)}</span>
            <span className="dia">{fechaEnPalabras(c.unlock_date)}</span>
          </p>
        )}

        {abierto && c.total > 0 && (
          <div className="lms-progress">
            <div className="lms-progress-track"><div className="lms-progress-bar" style={{ width: `${c.pct}%` }} /></div>
            <span className="lms-progress-label">{c.pct}%</span>
          </div>
        )}

        <div className="lms-course-foot">
          {abierto || vencido
            ? <>
                <span className="lms-lessons-chip">{c.done}/{c.total} pasos</span>
                <span className="go">
                  {vencido ? 'Renovar para entrar'
                    : !active && c.completed ? 'Volver a verlo →'
                    : c.completed ? 'Revisar →'
                    : 'Entrar →'}
                </span>
              </>
            : <span className="lms-lessons-chip muted">
                {porTerminar ? 'Casi lo tienes' : 'Muy pronto'}
              </span>}
        </div>
      </div>
    </>
  )

  // Ninguno de los cerrados es clickeable: llevar a una pantalla de error se
  // siente como una falla de la plataforma, no como una invitación.
  // Los que SÍ terminó siguen siendo link aunque la suscripción esté caída:
  // volver a armar un modelo que le gustó es lo que más se hace en ese estado.
  if (porTerminar || esperando) return <div className="lms-course-card bloqueado">{cuerpo}</div>
  if (vencido) return <div className="lms-course-card locked vencida">{cuerpo}</div>
  return <Link to={`/curso/${c.slug}`} className="lms-course-card">{cuerpo}</Link>
}

function DiplomaCard({ diploma: d }) {
  const [busy, setBusy] = useState(false)
  const download = async () => {
    setBusy(true)
    try { await openDiploma(d.id) } finally { setBusy(false) }
  }
  return (
    <div className={'lms-diploma-card' + (d.unlocked ? ' unlocked' : ' locked')}>
      <div className="lms-diploma-medal">{d.unlocked ? '🏅' : '🔒'}</div>
      <h3>{d.title}</h3>
      <p>{d.unlocked
        ? '¡Felicitaciones! Completaste esta etapa y ganaste tu diploma.'
        : 'Completa los cursos anteriores para desbloquear este diploma.'}</p>
      {d.unlocked
        ? <button className="lms-btn yellow" onClick={download} disabled={busy}>
            {busy ? <><Cargando />Preparando…</> : '🎓 Descargar diploma'}
          </button>
        : <span className="lms-diploma-locked-tag">Bloqueado</span>}
    </div>
  )
}
