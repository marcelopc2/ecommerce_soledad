"""
Otorgamiento de acceso al LMS cuando se confirma un pago, y correos asociados.
Mismos principios que la boleta: idempotente y no-bloqueante (el pago nunca
se rompe por un problema de LMS/email).
"""
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .models import Membership

User = get_user_model()


def grant_access_for_order(order):
    """
    Crea/extiende la membresía del comprador según los productos de la orden.
    - Idempotente: si la orden ya fue aplicada a la membresía, no vuelve a sumar meses.
    - No-bloqueante: nunca lanza excepción hacia el flujo de pago.
    Retorna la Membership o None si la orden no otorga cursos.
    """
    try:
        return _grant(order)
    except Exception:
        # No rompemos el pago por un fallo de LMS. Queda rastreable en el log del server.
        import traceback
        traceback.print_exc()
        return None


def _grant(order):
    products = list(order.products.all())
    courses = [c for p in products for c in p.courses.filter(is_active=True)]
    months = max((p.access_months for p in products), default=0)

    if not courses or months <= 0:
        return None  # la orden no incluye contenido LMS

    email = order.customer_email.lower().strip()
    user, user_created = User.objects.get_or_create(
        username=email,
        defaults={'email': email},
    )
    if user_created:
        user.set_unusable_password()  # definirá su clave con el link del correo
        user.save()

    membership, _ = Membership.objects.get_or_create(
        user=user,
        defaults={'expires_at': timezone.now()},
    )

    # Idempotencia: si esta orden ya fue aplicada (webhook + retorno duplicado), no re-sumar.
    if membership.orders.filter(pk=order.pk).exists():
        return membership

    base = membership.expires_at if membership.expires_at > timezone.now() else timezone.now()
    membership.expires_at = base + relativedelta(months=months)
    membership.save()
    membership.courses.add(*courses)
    membership.orders.add(order)

    if user_created or not user.has_usable_password():
        _send_welcome_email(user, membership)
    else:
        _send_extended_email(user, membership)

    return membership


def _set_password_link(user):
    """Link de un solo uso para definir/restablecer la contraseña (token estándar de Django)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/definir-clave/{uid}/{token}"


def _send_welcome_email(user, membership):
    link = _set_password_link(user)
    send_mail(
        subject='¡Bienvenido a IngenioBlocks! Activa tu acceso a los cursos',
        message=(
            f"¡Gracias por tu compra!\n\n"
            f"Tu cuenta fue creada con este correo ({user.email}) y ya tienes acceso a tus cursos.\n\n"
            f"Para entrar, primero define tu contraseña aquí:\n{link}\n\n"
            f"Tu acceso está activo hasta el {membership.expires_at:%d-%m-%Y}.\n\n"
            f"— IngenioBlocks"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _send_extended_email(user, membership):
    send_mail(
        subject='Tu acceso a IngenioBlocks fue extendido',
        message=(
            f"¡Gracias por tu compra!\n\n"
            f"Tu acceso a los cursos fue extendido: ahora está activo hasta el "
            f"{membership.expires_at:%d-%m-%Y}.\n\n"
            f"Entra con tu cuenta de siempre en {settings.FRONTEND_URL}/login\n\n"
            f"— IngenioBlocks"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def send_reset_email(user):
    """Correo de recuperación de contraseña (mismo link de un solo uso)."""
    link = _set_password_link(user)
    send_mail(
        subject='Restablece tu contraseña de IngenioBlocks',
        message=(
            f"Recibimos una solicitud para restablecer tu contraseña.\n\n"
            f"Define una nueva aquí:\n{link}\n\n"
            f"Si no fuiste tú, ignora este correo.\n\n— IngenioBlocks"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
