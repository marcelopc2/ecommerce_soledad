"""Modo soporte: alguien del equipo entra al Aula como un alumno, sin su clave,
para ver exactamente lo que él ve.

Es un token de acceso común del Aula (el mismo JWT del login) con dos marcas
extra: quién lo pidió y que es de soporte. Con esas marcas:

- Dura 30 minutos y no trae token de renovación: al vencer, se acabó.
- Es SOLO LECTURA: cualquier petición que no sea de lectura (comprar, cambiar
  la clave, marcar una clase vista, cancelar una suscripción...) se rechaza acá,
  en la autenticación, antes de llegar a la vista. Así no depende de que cada
  vista se acuerde de revisarlo.
- Si la cuenta de gestión que lo pidió se desactiva o deja de ser staff, el
  token deja de servir en el acto, aunque no haya vencido.

No se crea ningún token de renovación (RefreshToken), así que tampoco queda
como una "sesión" del alumno en la lista de tokens emitidos.
"""
from datetime import datetime, timedelta, timezone as tz

from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken

DURACION = timedelta(minutes=30)
MARCA_POR = 'soporte_por'        # correo de quien entró
MARCA_POR_ID = 'soporte_por_id'  # para revisar que siga siendo staff


def token_de_soporte(alumno, staff):
    token = AccessToken.for_user(alumno)
    token.set_exp(lifetime=DURACION)
    token[MARCA_POR] = staff.email or staff.get_username()
    token[MARCA_POR_ID] = staff.pk
    return str(token)


def datos_de_soporte(request):
    """{'por', 'vence'} si la petición viene en modo soporte; si no, None."""
    token = getattr(request, 'auth', None)
    if token is None or not hasattr(token, 'get') or not token.get(MARCA_POR):
        return None
    return {
        'por': token.get(MARCA_POR),
        'vence': datetime.fromtimestamp(token['exp'], tz=tz.utc).isoformat(),
    }


class JWTConModoSoporte(JWTAuthentication):
    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado is None:
            return None
        user, token = resultado
        if not token.get(MARCA_POR):
            return resultado

        staff_id = token.get(MARCA_POR_ID)
        if not get_user_model().objects.filter(pk=staff_id, is_active=True, is_staff=True).exists():
            raise exceptions.AuthenticationFailed('El acceso de soporte ya no es válido.')
        if request.method not in SAFE_METHODS:
            raise exceptions.PermissionDenied(
                'Modo soporte: solo puedes mirar. Para hacer cambios, entra desde el panel.'
            )
        return resultado
