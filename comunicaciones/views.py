"""La página donde cada cliente elige qué correos recibe.

Se llega por el enlace del pie de un correo, sin iniciar sesión (ver los enlaces
firmados en preferencias.py).

ABRIR EL ENLACE NO DA DE BAJA. Solo muestra la página; la baja requiere apretar
el botón. Es a propósito: Gmail y otros abren solos los enlaces de un correo
para revisar si son peligrosos -en los registros del servidor se ve al escáner
de Gmail entrando a los links segundos después de que llegan-. Si abrir el
enlace diera de baja, ese escáner daría de baja a la gente sin que tocara nada.
"""
from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .preferencias import (
    AULA, NOMBRES, NOVEDADES, dar_de_baja, esta_de_baja, leer_token,
    url_preferencias, volver_a_suscribir)


def _leer(token):
    try:
        return leer_token(token)
    except signing.BadSignature:
        # Un enlace alterado no dice nada de a quién pertenece: 404 y listo.
        raise Http404


@require_http_methods(['GET', 'POST'])
def preferencias(request, token):
    email, desde = _leer(token)

    if request.method == 'POST':
        if request.POST.get('accion') == 'baja_rapida':
            dar_de_baja(email, desde, origen='enlace')
        else:
            for categoria in NOMBRES:
                if request.POST.get(categoria) == 'on':
                    volver_a_suscribir(email, categoria)
                else:
                    dar_de_baja(email, categoria, origen='enlace')
        # Redirigir después de guardar: sin esto, recargar la página volvía a
        # mandar el formulario.
        return redirect(reverse('correos_preferencias', args=[token]) + '?guardado=1')

    opciones = [
        {'clave': NOVEDADES, 'titulo': 'Novedades de Ingenio Blocks',
         'detalle': 'Lanzamientos, modelos nuevos y noticias. Pocas veces al año.',
         'activa': not esta_de_baja(email, NOVEDADES)},
        {'clave': AULA, 'titulo': 'Avisos del Aula',
         'detalle': 'Cuando se abre un modelo nuevo para armar o se gana un diploma.',
         'activa': not esta_de_baja(email, AULA)},
    ]
    return render(request, 'comunicaciones/preferencias.html', {
        'email': email,
        'desde': desde,
        'desde_nombre': NOMBRES[desde],
        'desde_activa': not esta_de_baja(email, desde),
        'opciones': opciones,
        'guardado': request.GET.get('guardado') == '1',
        'contacto_email': settings.CONTACT_EMAIL,
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def baja_un_clic(request, token):
    """El botón "Cancelar suscripción" que Gmail muestra junto al remitente.

    Gmail lo manda como POST sin cookies ni formulario (RFC 8058), por eso va
    sin CSRF: el token firmado ya prueba que el enlace es de esa persona.
    Si alguien lo abre en el navegador (GET), se le muestra la página normal y
    no se toca nada, por el mismo motivo del escáner explicado arriba.
    """
    email, categoria = _leer(token)
    if request.method == 'GET':
        return redirect(reverse('correos_preferencias', args=[token]))
    dar_de_baja(email, categoria, origen='un_clic')
    return HttpResponse('Listo: no te volveremos a escribir sobre esto.',
                        content_type='text/plain; charset=utf-8')


class MiEnlaceDePreferencias(APIView):
    """Para "Mi cuenta": el mismo enlace del pie de los correos, para quien
    quiera cambiar sus preferencias sin esperar a que le llegue uno."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'url': url_preferencias(request.user.email, NOVEDADES)})
