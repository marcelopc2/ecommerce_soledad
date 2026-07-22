import { api } from '../api'

// El diploma es una página HTML protegida (requiere el JWT). No se puede abrir
// con un <a href> normal porque el navegador no manda el token, así que la
// bajamos con axios y la abrimos en una pestaña nueva vía blob URL. Desde ahí
// el usuario imprime / guarda como PDF.
export async function openDiploma(diplomaId) {
  const res = await api.get(`/lms/diplomas/${diplomaId}/download/`, { responseType: 'blob' })
  const url = URL.createObjectURL(new Blob([res.data], { type: 'text/html' }))
  const win = window.open(url, '_blank')
  if (!win) {
    // popup bloqueado: caemos a descarga directa del archivo
    const a = document.createElement('a')
    a.href = url
    a.download = 'diploma.html'
    a.click()
  }
  // liberamos el objeto luego de un rato (la pestaña ya lo cargó)
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
