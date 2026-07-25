from django.conf import settings


def sitio(request):
    """Expone la URL pública del sitio a las plantillas del panel.

    Va por settings y no por request.get_host() porque en desarrollo el sitio
    (Vite, :5173) y el panel (Django, :8000) corren en puertos distintos: armar
    el enlace desde el host de la petición llevaría al puerto equivocado.
    """
    return {'frontend_url': settings.FRONTEND_URL}
