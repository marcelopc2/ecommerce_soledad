"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from .views import health_check
from lms.urls import auth_urlpatterns, student_urlpatterns

# En producción conviene mover el admin a una ruta no obvia vía .env
# (ej. DJANGO_ADMIN_URL=gestion-interna-xyz/). En dev sigue siendo admin/.
ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'admin/')

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/catalog/', include('catalog.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/shipping/', include('shipments.urls')),
    path('api/auth/', include(auth_urlpatterns)),
    path('api/lms/', include(student_urlpatterns)),
    path('gestion/', include('panel.urls')),
]

# Portadas de los videos de la landing. Solo en desarrollo: en producción las
# sirve nginx (bloque `location /media/`), que es mucho más eficiente y además
# `static()` no hace nada con DEBUG=False.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Visor de las páginas de error (404/403/500/…). Con DEBUG=True Django
    # muestra su traceback en vez de estas plantillas, así que sin estas rutas
    # no habría forma de revisarlas mientras se trabaja. No existen en producción.
    from .error_previews import indice as _err_indice, preview as _err_preview
    from .email_previews import indice as _mail_indice, preview as _mail_preview
    urlpatterns += [
        path('dev/errores/', _err_indice, name='dev_errores'),
        path('dev/errores/<str:pagina>/', _err_preview, name='dev_error_preview'),
        path('dev/emails/', _mail_indice, name='dev_emails'),
        path('dev/emails/<str:nombre>/', _mail_preview, name='dev_email_preview'),
    ]
