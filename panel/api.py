"""Endpoint público que recibe las visitas del frontend.

Hace falta porque nginx sirve el React compilado como archivos estáticos: las
visitas a la portada y al Aula NUNCA pasan por Django, así que un middleware
no vería nada. Es el frontend el que avisa cada cambio de página.
"""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .registro import registrar_visita


class RegistrarVisitaView(APIView):
    """Anota una página vista. Público y silencioso: responde 204 pase lo que
    pase, para que un fallo de métricas jamás muestre un error a un visitante."""
    permission_classes = [AllowAny]
    throttle_scope = 'visita'

    def post(self, request):
        ruta = (request.data.get('ruta') or '/')[:200]
        referrer = (request.data.get('referrer') or '')[:500]
        registrar_visita(request, ruta, referrer)
        return Response(status=204)
