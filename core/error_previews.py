"""Visor de las páginas de error, SOLO para desarrollo.

Django únicamente usa 404.html / 403.html / 500.html cuando DEBUG=False; con
DEBUG=True muestra su propia página de depuración (el traceback amarillo). Eso
deja las plantillas de error sin forma de revisarse mientras se trabaja, que es
justo cuando uno las está diseñando.

Estas vistas renderizan las MISMAS plantillas que usará producción, con el mismo
código de estado, para poder verlas en local. Se registran solo si DEBUG=True
(ver core/urls.py), así que en producción estas rutas no existen.
"""
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

# (ruta, plantilla, código HTTP, etiqueta para el índice)
PAGINAS = [
    ('404', '404.html', 404, 'Página no encontrada'),
    ('403', '403.html', 403, 'Sin permiso'),
    ('403-csrf', '403_csrf.html', 403, 'Sesión vencida (CSRF)'),
    ('400', '400.html', 400, 'Solicitud inválida'),
    ('500', '500.html', 500, 'Error del servidor'),
    ('bloqueo', 'panel/lockout.html', 429, 'Acceso bloqueado (django-axes)'),
]


def preview(request, pagina):
    """Muestra una página de error tal como se verá en producción."""
    for ruta, plantilla, codigo, _ in PAGINAS:
        if ruta == pagina:
            # render_to_string sin request para 500.html: es exactamente como lo
            # hace Django en producción (contexto vacío, sin context processors),
            # así se detecta acá si la plantilla depende de algo del contexto.
            if plantilla == '500.html':
                return HttpResponse(render_to_string(plantilla), status=codigo)
            return render(request, plantilla, status=codigo)
    return HttpResponse('Página de error desconocida', status=404)


def indice(request):
    """Lista con enlaces a todas las páginas de error."""
    filas = ''.join(
        f'<li><a href="/dev/errores/{ruta}/"><b>{codigo}</b> — {etiqueta}</a>'
        f'<span>{plantilla}</span></li>'
        for ruta, plantilla, codigo, etiqueta in PAGINAS
    )
    return HttpResponse(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Páginas de error · desarrollo</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#f7f7f7; color:#0f172b;
         margin:0; padding:48px 20px; display:flex; justify-content:center; }}
  .caja {{ width:100%; max-width:640px; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  p.sub {{ color:#64748b; margin:0 0 24px; font-size:14px; line-height:1.6; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px;
        margin-bottom:10px; display:flex; align-items:center; justify-content:space-between;
        padding:14px 18px; }}
  li a {{ color:#8200db; text-decoration:none; font-weight:600; }}
  li a:hover {{ text-decoration:underline; }}
  li span {{ color:#94a3b8; font-size:12.5px; font-family:ui-monospace,monospace; }}
  .nota {{ margin-top:22px; font-size:13px; color:#64748b; line-height:1.7;
           background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px 18px; }}
  code {{ background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:12.5px; }}
</style></head><body>
<div class="caja">
  <h1>Páginas de error</h1>
  <p class="sub">Solo visibles en desarrollo. Se renderizan con la misma plantilla
     y el mismo código HTTP que usará producción.</p>
  <ul>{filas}</ul>
  <div class="nota">
    <b>Ojo:</b> con <code>DEBUG=True</code> Django muestra su página de depuración
    en los errores reales, no estas plantillas. Para ver el comportamiento
    definitivo hay que levantar con <code>DEBUG=False</code> en el <code>.env</code>.
    Estas rutas <b>no existen</b> en producción.
  </div>
</div>
</body></html>""")
