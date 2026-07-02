from django.urls import path
from .views import (
    CreateWebpayTransactionView, CommitWebpayTransactionView,
    CreateMercadoPagoTransactionView, CommitMercadoPagoTransactionView,
    MercadoPagoWebhookView
)

urlpatterns = [
    # Webpay Plus
    path('create/', CreateWebpayTransactionView.as_view(), name='webpay-create'),
    path('commit/', CommitWebpayTransactionView.as_view(), name='webpay-commit'),

    # MercadoPago
    path('mp-create/', CreateMercadoPagoTransactionView.as_view(), name='mp-create'),
    path('mp-commit/', CommitMercadoPagoTransactionView.as_view(), name='mp-commit'),
    path('mp-webhook/', MercadoPagoWebhookView.as_view(), name='mp-webhook'),
]
