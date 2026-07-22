from axes.handlers.proxy import AxesProxyHandler
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.http import urlsafe_base64_decode
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .serializers import ProfileSerializer
from .services import send_reset_email

User = get_user_model()


def _validate_new_password(password, user=None):
    """Valida con TODOS los validadores de Django (largo, comunes, numéricas, similitud).
    Retorna None si es válida, o el mensaje de error."""
    try:
        validate_password(password, user=user)
        return None
    except ValidationError as e:
        return ' '.join(e.messages)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login con email: mapeamos email→username (los usuarios se crean con username=email)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El frontend envía "email"; el campo username deja de ser obligatorio.
        self.fields[self.username_field].required = False

    def validate(self, attrs):
        email = self.initial_data.get('email', '').lower().strip()
        if email:
            attrs[self.username_field] = email
        return super().validate(attrs)


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_scope = 'login'  # anti fuerza bruta

    def post(self, request, *args, **kwargs):
        """django-axes YA bloquea el login por su cuenta (authenticate() deja de
        devolver usuario, así que ni la clave correcta entra). Lo que no logra es
        cambiar la RESPUESTA: marca el bloqueo sobre el Request de DRF, que
        envuelve al HttpRequest real, y AxesMiddleware nunca ve la marca. Sin
        esto el alumno bloqueado leería "contraseña incorrecta" y seguiría
        probando sin entender por qué nunca entra."""
        if AxesProxyHandler.is_locked(request._request, {'username': _login_email(request)}):
            minutos = int(settings.AXES_COOLOFF_TIME.total_seconds() // 60)
            return Response(
                {'error': f'Demasiados intentos fallidos. Por seguridad tu acceso quedó '
                          f'bloqueado por {minutos} minutos. Si olvidaste tu contraseña, '
                          f'usa "¿Olvidaste tu contraseña?" cuando se libere.',
                 'locked_out': True},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().post(request, *args, **kwargs)


def _login_email(request):
    """El correo con el que se está intentando entrar (axes cuenta por usuario+IP)."""
    data = request.data if hasattr(request, 'data') else {}
    return (data.get('email') or data.get('username') or '').lower().strip()


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        membership = getattr(user, 'membership', None)
        return Response({
            'email': user.email,
            'is_staff': user.is_staff,
            'membership': {
                'active': membership.is_active,
                'expires_at': membership.expires_at,
            } if membership else None,
        })


class ProfileView(APIView):
    """Perfil de la cuenta: ver y corregir los nombres.

    El nombre del alumno es el que sale IMPRESO en el diploma, y el diploma se
    arma al momento de abrirlo: si el apoderado corrige un típeo acá, los
    diplomas ya obtenidos salen corregidos también (no hay nada congelado).

    Solo se puede tocar la membresía propia: se obtiene desde request.user, no
    de un id que venga en la petición.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(self._datos(request.user))

    def patch(self, request):
        membership = getattr(request.user, 'membership', None)
        if membership is None:
            return Response({'error': 'Tu cuenta todavía no tiene una membresía activa.'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = ProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        if 'student_name' in datos:
            membership.student_name = datos['student_name']
        if 'parent_name' in datos:
            membership.parent_name = datos['parent_name']
        membership.save()

        return Response(self._datos(request.user))

    def _datos(self, user):
        m = getattr(user, 'membership', None)
        return {
            # El correo NO se edita acá: es la identidad de la cuenta (el
            # username) y cambiarlo rompería el acceso y el historial de compras.
            'email': user.email,
            'student_name': m.student_name if m else '',
            'parent_name': m.parent_name if m else '',
            'membership': {
                'active': m.is_active,
                'expires_at': m.expires_at,
            } if m else None,
        }


class SetPasswordView(APIView):
    """Define/restablece la contraseña con el link de un solo uso enviado por correo."""
    permission_classes = [AllowAny]
    throttle_scope = 'password'

    def post(self, request):
        uid = request.data.get('uid', '')
        token = request.data.get('token', '')
        password = request.data.get('password', '')

        try:
            user = User.objects.get(pk=urlsafe_base64_decode(uid).decode())
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Link inválido'}, status=status.HTTP_400_BAD_REQUEST)

        error = _validate_new_password(password, user)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({'error': 'El link expiró o ya fue usado. Solicita uno nuevo.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()
        return Response({'ok': True, 'email': user.email})


class RequestResetView(APIView):
    """Solicita correo de recuperación. Siempre responde 200 (no revela si el email existe)."""
    permission_classes = [AllowAny]
    throttle_scope = 'reset'  # anti spam de correos

    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        if email:
            try:
                send_reset_email(User.objects.get(username=email))
            except User.DoesNotExist:
                pass
        return Response({'ok': True})


class ChangePasswordView(APIView):
    """Cambio de contraseña estando logueado (pide la actual)."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'password'

    def post(self, request):
        current = request.data.get('current_password', '')
        new = request.data.get('new_password', '')

        if not request.user.check_password(current):
            return Response({'error': 'La contraseña actual no es correcta'},
                            status=status.HTTP_400_BAD_REQUEST)

        error = _validate_new_password(new, request.user)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new)
        request.user.save()
        return Response({'ok': True})
