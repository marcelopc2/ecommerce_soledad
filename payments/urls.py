from django.urls import path
from .views import (
    CreateWebpayTransactionView, CommitWebpayTransactionView,
    CreateMercadoPagoTransactionView, CommitMercadoPagoTransactionView,
    MercadoPagoWebhookView, ValidarCuponView,
    CreateOneclickView, FinishOneclickView, MisSuscripcionesView, CancelarSuscripcionView,
    MisTarjetasView, PagarConTarjetaGuardadaView,
)

urlpatterns = [
    # Webpay Plus
    path('create/', CreateWebpayTransactionView.as_view(), name='webpay-create'),
    path('commit/', CommitWebpayTransactionView.as_view(), name='webpay-commit'),

    # MercadoPago
    path('mp-create/', CreateMercadoPagoTransactionView.as_view(), name='mp-create'),
    path('mp-commit/', CommitMercadoPagoTransactionView.as_view(), name='mp-commit'),
    path('mp-webhook/', MercadoPagoWebhookView.as_view(), name='mp-webhook'),

    # Transbank Oneclick (tarjeta inscrita; también las suscripciones)
    path('oneclick/create/', CreateOneclickView.as_view(), name='oneclick-create'),
    path('oneclick/finish/', FinishOneclickView.as_view(), name='oneclick-finish'),
    path('oneclick/tarjetas/', MisTarjetasView.as_view(), name='mis-tarjetas'),
    path('oneclick/pagar-guardada/', PagarConTarjetaGuardadaView.as_view(), name='oneclick-guardada'),
    path('suscripciones/', MisSuscripcionesView.as_view(), name='mis-suscripciones'),
    path('suscripciones/<int:pk>/cancelar/', CancelarSuscripcionView.as_view(), name='suscripcion-cancelar'),

    # Revisa un cupón sin cobrar nada, para mostrar el descuento en el resumen.
    path('cupon/', ValidarCuponView.as_view(), name='cupon-validar'),
]
