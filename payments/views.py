import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from .models import Order
from .orders import build_order_from_request
from .services import create_webpay_transaction, commit_webpay_transaction
from invoicing.services import issue_invoice_for_order
from lms.services import grant_access_for_order

# Va al archivo pagos.log, separado del log general: es el rastro que permite
# reconstruir qué pasó cuando alguien reclama "pagué y no me llegó nada".
log = logging.getLogger('ingenioblocks.pagos')


def _entregar_compra(order):
    """Emite la boleta y otorga el acceso al LMS de una orden ya pagada.

    Cada paso va en su propio try: que falle la boleta NO puede impedir que el
    alumno reciba su acceso, y viceversa. La orden ya está en PAID y guardada
    antes de llegar acá, así que un fallo de estos deja la venta registrada y
    recuperable a mano desde el panel.
    """
    try:
        issue_invoice_for_order(order)
    except Exception:
        log.exception('Falló la emisión de boleta de la orden %s', order.order_id)

    try:
        grant_access_for_order(order)
    except Exception:
        log.exception('Falló el otorgamiento de acceso de la orden %s', order.order_id)

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
        except Exception:
            # El detalle va al log, no al navegador: str(e) de la SDK de
            # Transbank puede traer credenciales y rutas internas.
            log.exception('No se pudo iniciar el pago Webpay de la orden %s', order.order_id)
            return Response(
                {'error': 'No pudimos conectar con Webpay. Intenta nuevamente en unos minutos.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

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

        # Confirmar en Transbank.
        #
        # OJO: commit_webpay_transaction() es la llamada que COBRA. Si lanza una
        # excepción no sabemos de qué lado quedó: puede no haber cobrado nada, o
        # puede haber cobrado y habérsenos caído la red al recibir la respuesta.
        # El token es de un solo uso, así que no se puede reintentar. Por eso el
        # except deja la orden en REVIEW y no en FAILED: dar por perdida una
        # compra que sí se cobró es peor que pedir una revisión manual.
        try:
            response = commit_webpay_transaction(token_ws)
        except Exception:
            order.status = 'REVIEW'
            order.save(update_fields=['status', 'updated_at'])
            log.exception(
                'REVISAR A MANO: el commit de Webpay falló para la orden %s '
                '(token %s, monto %s). Puede haberse cobrado igual: confirmar en '
                'el portal de Transbank antes de decidir.',
                order.order_id, token_ws, order.total_amount,
            )
            return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=error')

        if response.get('status') == 'AUTHORIZED':
            order.status = 'PAID'
            order.save(update_fields=['status', 'updated_at'])
            log.info('Orden %s PAGADA por Webpay (monto %s)', order.order_id, order.total_amount)
            _entregar_compra(order)
            return redirect(f'{settings.FRONTEND_URL}/checkout/success?order={order.order_id}')

        order.status = 'FAILED'
        order.save(update_fields=['status', 'updated_at'])
        log.info('Orden %s rechazada por Webpay (status %s)', order.order_id, response.get('status'))
        return redirect(f'{settings.FRONTEND_URL}/checkout/failed?reason=rejected')

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
        except Exception:
            log.exception('No se pudo crear la preferencia de MercadoPago de la orden %s',
                          order.order_id)
            return Response(
                {'error': 'No pudimos conectar con MercadoPago. Intenta nuevamente en unos minutos.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

def _verify_and_update_order(payment_id):
    """
    Consulta el pago real en MercadoPago y actualiza la orden en consecuencia.
    FUENTE DE VERDAD: el estado lo decide la API de MercadoPago, no el navegador.
    Retorna (order, real_status) o (None, None) si no se pudo resolver.
    """
    if not payment_id or str(payment_id).lower() in ('', 'null', 'none'):
        return None, None

    try:
        payment = get_mercadopago_payment(payment_id)
    except Exception:
        log.exception('No se pudo consultar el pago %s en MercadoPago', payment_id)
        return None, None

    real_status = payment.get('status')  # approved / rejected / pending / in_process ...
    external_reference = payment.get('external_reference')

    if not external_reference:
        return None, real_status

    # El webhook server-to-server y la vuelta del navegador llegan casi a la vez
    # y los dos entran acá. select_for_update serializa a los dos procesos sobre
    # la misma fila: sin esto ambos podían pasar el chequeo de idempotencia de
    # grant_access_for_order antes de que ninguno lo marcara, y la membresía
    # terminaba con el doble de meses.
    entregar = False
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_id=external_reference)
        except Order.DoesNotExist:
            return None, real_status

        # Verificamos que el monto cobrado coincida con el de la orden (anti-manipulación).
        paid_amount = payment.get('transaction_amount')
        if paid_amount is not None and int(paid_amount) != int(order.total_amount):
            order.status = 'FAILED'
            order.save(update_fields=['status', 'updated_at'])
            log.error(
                'MONTO NO COINCIDE en la orden %s: MercadoPago cobró %s y la orden dice %s',
                order.order_id, paid_amount, order.total_amount,
            )
            return order, 'amount_mismatch'

        if real_status == 'approved':
            # Solo entregamos si la orden NO estaba ya pagada. Así el segundo en
            # llegar (webhook o navegador, da igual el orden) no re-entrega.
            if order.status != 'PAID':
                order.status = 'PAID'
                order.save(update_fields=['status', 'updated_at'])
                entregar = True
                log.info('Orden %s PAGADA por MercadoPago (monto %s)',
                         order.order_id, order.total_amount)
        elif real_status in ('rejected', 'cancelled'):
            order.status = 'FAILED'
            order.save(update_fields=['status', 'updated_at'])
            log.info('Orden %s rechazada por MercadoPago (status %s)',
                     order.order_id, real_status)
        # pending / in_process: la orden queda como está (PENDING) hasta el webhook definitivo.

    # Fuera de la transacción: emitir boleta y otorgar acceso implican llamadas
    # HTTP y envío de correo, que no deben mantener abierto un bloqueo de fila.
    if entregar:
        _entregar_compra(order)

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
