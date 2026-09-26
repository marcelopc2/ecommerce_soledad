"""Bajo /api/correos/ y no en una dirección propia: nginx solo le pasa a Django
lo que empieza con /api, /gestion o /admin. Todo lo demás lo atiende la tienda
en React, que no conoce estas páginas y mostraría un "no encontrado"."""
from django.urls import path

from . import views

urlpatterns = [
    path('preferencias/<str:token>/', views.preferencias, name='correos_preferencias'),
    path('baja/<str:token>/', views.baja_un_clic, name='correos_baja'),
    path('mi-enlace/', views.MiEnlaceDePreferencias.as_view(), name='correos_mi_enlace'),
]
