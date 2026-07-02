import os
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.integration_type import IntegrationType

from transbank.common.options import WebpayOptions

def get_webpay_transaction():
    """
    Configura y retorna la instancia de Transacción de Webpay Plus.
    Ambiente según TBK_ENVIRONMENT en .env: INTEGRACION (pruebas, default) o PRODUCCION.
    Las llaves por defecto son las de integración PÚBLICAS de Transbank (documentadas).
    """
    commerce_code = os.environ.get("TBK_API_KEY_ID", "597055555532")
    api_key = os.environ.get("TBK_API_KEY_SECRET", "579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C")

    environment = os.environ.get("TBK_ENVIRONMENT", "INTEGRACION").upper()
    integration_type = IntegrationType.LIVE if environment == "PRODUCCION" else IntegrationType.TEST

    options = WebpayOptions(commerce_code, api_key, integration_type)
    return Transaction(options)

def create_webpay_transaction(buy_order, session_id, amount, return_url):
    """
    Crea una transacción en Transbank y retorna la URL y el Token.
    """
    tx = get_webpay_transaction()
    response = tx.create(
        buy_order=str(buy_order),
        session_id=str(session_id),
        amount=amount,
        return_url=return_url
    )
    return response

def commit_webpay_transaction(token_ws):
    """
    Confirma una transacción en Transbank (Paso crucial para cobrar).
    """
    tx = get_webpay_transaction()
    response = tx.commit(token=token_ws)
    return response

# --- MERCADOPAGO SERVICES --- #
import mercadopago

def get_mercadopago_sdk():
    """Inicializa el SDK de MercadoPago con el token del .env"""
    access_token = os.environ.get('MP_ACCESS_TOKEN', 'TEST-TOKEN')
    return mercadopago.SDK(access_token)

def create_mercadopago_preference(order_id, title, amount, return_url, notification_url=None):
    """
    Crea una Preferencia de Pago en MercadoPago.
    Esto devuelve un 'init_point' que es la URL donde el usuario debe pagar.
    """
    sdk = get_mercadopago_sdk()

    preference_data = {
        "items": [
            {
                "title": title,
                "quantity": 1,
                "unit_price": float(amount)
            }
        ],
        "back_urls": {
            "success": return_url,
            "failure": return_url,
            "pending": return_url
        },
        "auto_return": "approved",
        "external_reference": str(order_id) # Nuestro ID de orden para identificarla cuando vuelva
    }

    # Webhook: MercadoPago notifica aquí (server-to-server) el estado real del pago.
    if notification_url:
        preference_data["notification_url"] = notification_url

    preference_response = sdk.preference().create(preference_data)

    response_data = preference_response.get("response", {})
    init_point = response_data.get("init_point")

    if not init_point:
        raise Exception(f"MercadoPago Error: {response_data}")

    return init_point

def get_mercadopago_payment(payment_id):
    """
    Consulta un pago en la API de MercadoPago por su ID.
    Es la FUENTE DE VERDAD para confirmar un pago: nunca confiamos en los
    parámetros que vienen en la URL de retorno (son falsificables).
    Retorna el dict del pago (incluye 'status', 'external_reference', 'transaction_amount', etc.)
    """
    sdk = get_mercadopago_sdk()
    response = sdk.payment().get(payment_id)
    return response.get("response", {})
