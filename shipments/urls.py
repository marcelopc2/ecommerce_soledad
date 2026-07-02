from django.urls import path
from .views import QuoteShippingView, CommunesView

urlpatterns = [
    path('quote/', QuoteShippingView.as_view(), name='shipments-quote'),
    path('communes/', CommunesView.as_view(), name='shipments-communes'),
]
