/*
 * Genera public/robots.txt y public/sitemap.xml desde VITE_SITE_URL.
 *
 * Corre antes de `vite build` (ver el script "build" en package.json). Así el
 * dominio vive en UN solo lugar (.env.production): al pasar al dominio real de
 * producción se cambia esa variable y estos dos archivos se regeneran solos,
 * sin riesgo de que el sitemap siga apuntando al dominio de pruebas.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function siteUrl() {
  if (process.env.VITE_SITE_URL) return process.env.VITE_SITE_URL
  // Modo build = production, así que se lee de .env.production.
  try {
    const env = readFileSync(resolve(raiz, '.env.production'), 'utf8')
    const m = env.match(/^\s*VITE_SITE_URL\s*=\s*(.+)\s*$/m)
    if (m) return m[1].trim()
  } catch { /* sin archivo: cae al default */ }
  return 'https://ecommercesoledad.duckdns.org'
}

const SITE = siteUrl().replace(/\/$/, '')

const robots = `# Generado por scripts/gen-seo.mjs desde VITE_SITE_URL — no editar a mano.
User-agent: *
Allow: /

# Zonas privadas: no tiene sentido indexarlas.
Disallow: /gestion/
Disallow: /admin/
Disallow: /checkout
Disallow: /mis-cursos
Disallow: /mi-cuenta
Disallow: /curso/
Disallow: /definir-clave/
Allow: /legal/

Sitemap: ${SITE}/sitemap.xml
`

// Sitio de una sola página pública + las legales. Cuando existan páginas
// propias por kit, conviene generar esto desde el catálogo.
const rutas = [
  { loc: '/', changefreq: 'weekly', priority: '1.0' },
  { loc: '/legal/terminos', changefreq: 'yearly', priority: '0.3' },
  { loc: '/legal/privacidad', changefreq: 'yearly', priority: '0.3' },
  { loc: '/legal/retracto', changefreq: 'yearly', priority: '0.3' },
]

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<!-- Generado por scripts/gen-seo.mjs — no editar a mano. -->
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${rutas.map(r => `  <url>
    <loc>${SITE}${r.loc}</loc>
    <changefreq>${r.changefreq}</changefreq>
    <priority>${r.priority}</priority>
  </url>`).join('\n')}
</urlset>
`

writeFileSync(resolve(raiz, 'public/robots.txt'), robots)
writeFileSync(resolve(raiz, 'public/sitemap.xml'), sitemap)
console.log(`[gen-seo] robots.txt y sitemap.xml generados para ${SITE}`)
