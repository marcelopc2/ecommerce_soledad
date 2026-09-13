from django.urls import path
from .views import (
    CreateWebpayTransactionView, CommitWebpayTransactionView,
    CreateMercadoPagoTransactionView, CommitMercadoPagoTransactionView,
    MercadoPagoWebhookView, ValidarCuponView,
)

urlpatterns = [
    # Webpay Plus
    path('create/', CreateWebpayTransactionView.as_view(), name='webpay-create'),
    path('commit/', CommitWebpayTransactionView.as_view(), name='webpay-commit'),

    # MercadoPago
    path('mp-create/', CreateMercadoPagoTransactionView.as_view(), name='mp-create'),
    path('mp-commit/', CommitMercadoPagoTransactionView.as_view(), name='mp-commit'),
    path('mp-webhook/', MercadoPagoWebhookView.as_view(), name='mp-webhook'),

    # Revisa un cupón sin cobrar nada, para mostrar el descuento en el resumen.
    path('cupon/', ValidarCuponView.as_view(), name='cupon-validar'),
]
