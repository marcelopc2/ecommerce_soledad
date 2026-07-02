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
