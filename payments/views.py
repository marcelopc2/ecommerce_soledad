import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from .models import Order
from .orders import build_order_from_request
from .services import create_webpay_transaction, commit_webpay_transaction
from invoicing.services import issue_invoice_for_order
from lms.services import grant_access_for_order

class CreateWebpayTransactionView(APIView):
    throttle_scope = 'payment'

    def post(self, request):
        # Arma la orden (+ envío si corresponde) y valida el costo de envío en el servidor.
        order, error = build_order_from_request(request.data, user=request.user)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        # Configurar URL de retorno (a este mismo servidor de Django)
        # request.build_absolute_uri() asegura que se incluye el dominio correcto (ej. http://127.0.0.1:8000)
        return_url = request.build_absolute_uri(reverse('webpay-commit'))

        # Llamar a Transbank
        try:
            response = create_webpay_transaction(
                buy_order=str(order.order_id)[:26], # TBK buy_order max length is 26
                session_id=str(order.id),
                amount=int(order.total_amount),
                return_url=return_url
            )
            
            # response contiene { "url": "https://webpay3gint...", "token": "..." }
            order.tbk_token = response['token']
            order.save()
            
            return Response({
                'url': response['url'],
                'token': response['token']
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CommitWebpayTransactionView(APIView):
    """
    Este endpoint recibe la redirección de Transbank después del pago.
    En Transbank Webpay Plus, la redirección puede ser GET o POST dependiendo de si el pago se anuló o aceptó.
    """
    def get(self, request):
        return self.process_commit(request)

    def post(self, request):
        return self.process_commit(request)

    def process_commit(self, request):
        # Transbank envía el token en GET o POST
        token_ws = request.GET.get('token_ws') or request.POST.get('token_ws')
        
        # Si no hay token, el usuario abortó el pago en la página de Webpay
        if not token_ws:
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=aborted')

        # Buscar la orden
        try:
            order = Order.objects.get(tbk_token=token_ws)
        except Order.DoesNotExist:
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=invalid_token')

        # Confirmar en Transbank
        try:
            response = commit_webpay_transaction(token_ws)

            if response.get('status') == 'AUTHORIZED':
                order.status = 'PAID'
                order.save()
                # Emitir boleta electrónica (no-bloqueante: si falla queda en ERROR para reintentar).
                issue_invoice_for_order(order)
                # Otorgar acceso al LMS (crea/extiende membresía y envía el correo de acceso).
                grant_access_for_order(order)
                return redirect(f'{settings.FRONTEND_URL}/checkout/success?order={order.order_id}')
            else:
                order.status = 'FAILED'
                order.save()
                return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=rejected')

        except Exception as e:
            order.status = 'FAILED'
            order.save()
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=error')

from .services import create_mercadopago_preference, get_mercadopago_payment

class CreateMercadoPagoTransactionView(APIView):
    throttle_scope = 'payment'

    def post(self, request):
        # Arma la orden (+ envío si corresponde) y valida el costo de envío en el servidor.
        order, error = build_order_from_request(request.data, user=request.user)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        # MercadoPago exige URLs públicas con HTTPS para el retorno y el webhook.
        # Usamos la URL del túnel (BACKEND_PUBLIC_URL); si no está configurada, caemos a la local.
        base_url = settings.BACKEND_PUBLIC_URL or request.build_absolute_uri('/').rstrip('/')
        return_url = f"{base_url}{reverse('mp-commit')}"
        notification_url = f"{base_url}{reverse('mp-webhook')}"

        try:
            init_point = create_mercadopago_preference(
                order_id=order.order_id,
                title=f"Pedido IngenioBlocks #{str(order.order_id)[:8]}",
                amount=order.total_amount,
                return_url=return_url,
                notification_url=notification_url
            )
            return Response({'url': init_point})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def _verify_and_update_order(payment_id):
    """
    Consulta el pago real en MercadoPago y actualiza la orden en consecuencia.
    FUENTE DE VERDAD: el estado lo decide la API de MercadoPago, no el navegador.
    Retorna (order, real_status) o (None, None) si no se pudo resolver.
    """
    if not payment_id or str(payment_id).lower() in ('', 'null', 'none'):
        return None, None

    payment = get_mercadopago_payment(payment_id)
    real_status = payment.get('status')  # approved / rejected / pending / in_process ...
    external_reference = payment.get('external_reference')

    if not external_reference:
        return None, real_status

    try:
        order = Order.objects.get(order_id=external_reference)
    except Order.DoesNotExist:
        return None, real_status

    # Verificamos que el monto cobrado coincida con el de la orden (anti-manipulación).
    paid_amount = payment.get('transaction_amount')
    if paid_amount is not None and int(paid_amount) != int(order.total_amount):
        order.status = 'FAILED'
        order.save()
        return order, 'amount_mismatch'

    if real_status == 'approved':
        order.status = 'PAID'
        order.save()
        # Emitir boleta electrónica (no-bloqueante: si falla queda en ERROR para reintentar).
        issue_invoice_for_order(order)
        # Otorgar acceso al LMS (crea/extiende membresía y envía el correo de acceso).
        grant_access_for_order(order)
        return order, real_status
    elif real_status in ('rejected', 'cancelled'):
        order.status = 'FAILED'
    # pending / in_process: dejamos la orden como está (PENDING) hasta el webhook definitivo
    order.save()
    return order, real_status


class CommitMercadoPagoTransactionView(APIView):
    """
    back_url: MercadoPago redirige aquí el navegador del usuario tras pagar.
    Solo lo usamos para UX (redirigir a success/failed). NO confiamos en el
    ?status de la URL: verificamos el pago real contra la API de MercadoPago.
    """
    def get(self, request):
        payment_id = request.GET.get('payment_id') or request.GET.get('collection_id')
        external_reference = request.GET.get('external_reference')

        order, real_status = _verify_and_update_order(payment_id)

        # Fallback: si no vino payment_id (usuario canceló antes de pagar), usamos la orden por referencia.
        if order is None and external_reference:
            try:
                order = Order.objects.get(order_id=external_reference)
            except Order.DoesNotExist:
                order = None

        if order is None:
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=invalid_order')

        if real_status == 'approved':
            return redirect(f'{settings.FRONTEND_URL}/checkout/success?order={order.order_id}')
        else:
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason={real_status or "not_approved"}')


class MercadoPagoWebhookView(APIView):
    """
    Webhook server-to-server de MercadoPago. Es la confirmación DEFINITIVA del pago:
    llega aunque el usuario cierre el navegador antes de volver al sitio.
    """
    def post(self, request):
        topic = request.GET.get('type') or request.GET.get('topic') or (request.data.get('type') if hasattr(request.data, 'get') else None)

        # Solo nos interesan notificaciones de pago.
        if topic != 'payment':
            return Response(status=status.HTTP_200_OK)

        # El id del pago puede venir en el body (data.id) o en el query (data.id / id).
        payment_id = None
        data = request.data if hasattr(request.data, 'get') else {}
        if isinstance(data.get('data'), dict):
            payment_id = data['data'].get('id')
        payment_id = payment_id or request.GET.get('data.id') or request.GET.get('id')

        _verify_and_update_order(payment_id)

        # Siempre respondemos 200 para que MercadoPago no reintente indefinidamente.
        return Response(status=status.HTTP_200_OK)
