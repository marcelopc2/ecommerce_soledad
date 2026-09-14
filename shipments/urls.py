from django.urls import path
from .views import QuoteShippingView, CommunesView, PuntoRetiroView

urlpatterns = [
    path('quote/', QuoteShippingView.as_view(), name='shipments-quote'),
    path('communes/', CommunesView.as_view(), name='shipments-communes'),
    path('retiro/', PuntoRetiroView.as_view(), name='shipments-retiro'),
]
