"""Visor de los correos, SOLO para desarrollo.

Con EMAIL_BACKEND=console los correos salen por la consola del runserver, así
que el HTML no hay dónde mirarlo; y con SMTP real habría que provocar una
compra de verdad cada vez que se ajusta un margen. Estas vistas renderizan las
mismas plantillas con datos de ejemplo.

Se registran solo si DEBUG=True (ver core/urls.py): en producción no existen.
"""
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .emails import GRID_PATH, LOGO_PATH, formato_clp


def _data_uri(ruta):
    """El HTML real referencia las imágenes como `cid:` (adjuntos en línea), que
    solo resuelven dentro de un cliente de correo. En el navegador se muestran
    incrustadas como data URI para poder revisar el diseño."""
    if not ruta.exists():
        return ''
    import base64
    return 'data:image/png;base64,' + base64.b64encode(ruta.read_bytes()).decode()

_LINK = f'{settings.FRONTEND_URL}/mis-cursos'
_CLAVE = f'{settings.FRONTEND_URL}/definir-clave/MQ/abc123-ejemplo'

# Datos de ejemplo por correo. Se busca que se parezcan a los reales: nombres
# largos, precios de verdad y textos que puedan desbordar, para que el diseño
# se pruebe con contenido plausible y no con "Lorem ipsum" corto.
EJEMPLOS = {
    'bienvenida': {
        'etiqueta': 'Bienvenida (cuenta nueva tras la compra)',
        'asunto': '¡Bienvenido a Ingenio Blocks! Activa tu acceso',
        'ctx': {
            'nombre': 'Francisca',
            'email': 'francisca.rojas@ejemplo.cl',
            'link': _CLAVE,
            'vigencia_texto': 'Tu acceso está activo hasta el 20-07-2027.',
        },
    },
    'acceso_extendido': {
        'etiqueta': 'Acceso extendido (ya tenía cuenta)',
        'asunto': 'Tu acceso a Ingenio Blocks fue extendido',
        'ctx': {
            'nombre': 'Francisca',
            'link': _LINK,
            'vigencia_texto': 'Ahora tu acceso está activo hasta el 20-01-2028.',
        },
    },
    'recuperar_clave': {
        'etiqueta': 'Recuperar contraseña',
        'asunto': 'Restablece tu contraseña de Ingenio Blocks',
        'ctx': {'link': _CLAVE},
    },
    'compra_confirmada': {
        'etiqueta': 'Compra confirmada (detalle del pedido)',
        'asunto': 'Confirmación de tu compra · Ingenio Blocks',
        'ctx': {
            'numero_pedido': 'a3f9c1e8',
            'productos': [
                {'nombre': 'Kit Inicial Ingenio Blocks (400+ piezas)', 'precio': formato_clp(69490)},
                {'nombre': 'Pack 8 Modelos Extra', 'precio': formato_clp(12900)},
            ],
            'envio_costo': formato_clp(4990),
            'envio_courier': 'Starken',
            'total': formato_clp(87380),
            'tiene_envio': True,
            'tiene_acceso': True,
            'link': _LINK,
        },
    },
    'envio_despachado': {
        'etiqueta': 'Envío despachado (tracking)',
        'asunto': '¡Tu kit va en camino! · Ingenio Blocks',
        'ctx': {
            'nombre': 'Francisca',
            'courier': 'Starken',
            'tracking': '778901234567',
            'destino': 'Viña del Mar, Valparaíso',
            'tracking_url': 'https://www.starken.cl/seguimiento',
            'estimado': 'Llegada estimada: 2 a 3 días hábiles.',
        },
    },
    'curso_desbloqueado': {
        'etiqueta': 'Nuevo modelo desbloqueado (goteo semanal)',
        'asunto': '¡Se desbloqueó un modelo nuevo! · Ingenio Blocks',
        'ctx': {
            'saludo': 'Hola Francisca, esta semana Matías puede construir un modelo nuevo:',
            'numero': 4,
            'curso_titulo': 'Centrífuga de Ropa Motorizada',
            'curso_descripcion': 'Descubre cómo este ingenioso mecanismo transforma la tarea de lavar en un proceso rápido y eficiente.',
            'link': f'{settings.FRONTEND_URL}/curso/centrifuga-de-ropa',
        },
    },
    'diploma_obtenido': {
        'etiqueta': 'Diploma obtenido',
        'asunto': '¡Conseguiste un diploma! · Ingenio Blocks',
        'ctx': {
            'nombre': 'Matías',
            'diploma_titulo': 'Diploma Nivel Básico — Mecánica y Movimiento',
            'fecha': timezone.now().strftime('%d-%m-%Y'),
            'link': _LINK,
        },
    },
    'contacto_interno': {
        'etiqueta': 'Contacto desde la web (llega a la clienta)',
        'asunto': 'Contacto desde la web · Camila Soto',
        'ctx': {
            'nombre': 'Camila Soto',
            'email': 'camila.soto@ejemplo.cl',
            'telefono': '+56 9 1234 5678',
            'comentarios': 'Hola, quería saber si el kit inicial sirve para una niña de 6 años '
                           'y si hacen despacho a Antofagasta. ¡Gracias!',
        },
    },
}


def preview(request, nombre):
    """Muestra un correo. Con ?txt=1 muestra la versión de texto plano."""
    ejemplo = EJEMPLOS.get(nombre)
    if ejemplo is None:
        return HttpResponse('Correo desconocido', status=404)

    ctx = dict(ejemplo['ctx'])
    ctx.setdefault('contacto_email', settings.CONTACT_EMAIL)
    ctx.setdefault('frontend_url', settings.FRONTEND_URL)
    ctx.setdefault('logo_src', _data_uri(LOGO_PATH))
    ctx.setdefault('grid_src', _data_uri(GRID_PATH))

    if request.GET.get('txt'):
        cuerpo = render_to_string(f'emails/{nombre}.txt', ctx)
        return HttpResponse(cuerpo, content_type='text/plain; charset=utf-8')
    return HttpResponse(render_to_string(f'emails/{nombre}.html', ctx))


def indice(request):
    filas = ''.join(
        f'<li><div><b>{d["etiqueta"]}</b><span>{d["asunto"]}</span></div>'
        f'<div class="links">'
        f'<a href="/dev/emails/{k}/">HTML</a>'
        f'<a href="/dev/emails/{k}/?txt=1" class="txt">texto</a>'
        f'</div></li>'
        for k, d in EJEMPLOS.items()
    )
    return HttpResponse(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Correos · desarrollo</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#f7f7f7; color:#0f172b;
         margin:0; padding:48px 20px; display:flex; justify-content:center; }}
  .caja {{ width:100%; max-width:720px; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  p.sub {{ color:#64748b; margin:0 0 24px; font-size:14px; line-height:1.6; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px;
        margin-bottom:10px; display:flex; align-items:center; justify-content:space-between;
        gap:16px; padding:14px 18px; }}
  li b {{ display:block; font-size:14.5px; }}
  li span {{ display:block; color:#94a3b8; font-size:12.5px; margin-top:3px; }}
  .links {{ display:flex; gap:8px; flex-shrink:0; }}
  .links a {{ color:#8200db; text-decoration:none; font-weight:600; font-size:13px;
              border:1.5px solid #e9d5ff; border-radius:8px; padding:7px 14px; }}
  .links a:hover {{ background:#f8f4fe; }}
  .links a.txt {{ color:#64748b; border-color:#e2e8f0; }}
  .nota {{ margin-top:22px; font-size:13px; color:#64748b; line-height:1.7;
           background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px 18px; }}
  code {{ background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:12.5px; }}
</style></head><body>
<div class="caja">
  <h1>Correos del sitio</h1>
  <p class="sub">Solo visibles en desarrollo. Se renderizan con las mismas
     plantillas que usa el envío real, con datos de ejemplo.</p>
  <ul>{filas}</ul>
  <div class="nota">
    Cada correo se manda como <b>multipart</b>: la versión HTML y la de texto
    plano viajan juntas y el cliente elige cuál mostrar. Conviene revisar las dos
    (los filtros de spam penalizan el HTML sin alternativa de texto).<br><br>
    En desarrollo <code>EMAIL_BACKEND</code> es la consola: los correos reales
    aparecen en la terminal del <code>runserver</code>, no se envía nada.
  </div>
</div>
</body></html>""")
