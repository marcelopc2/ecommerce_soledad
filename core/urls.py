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
from django.contrib import admin
from django.urls import path, include
from .views import health_check
from lms.urls import auth_urlpatterns, student_urlpatterns, cms_urlpatterns

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
    path('api/cms/', include(cms_urlpatterns)),
]
