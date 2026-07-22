from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from catalog.models import Product
from .services import (
    get_shipping_quotes, get_communes, build_package_from_products,
    CotizacionNoDisponible,
)


class CommunesView(APIView):
    """Regiones y comunas para el selector del checkout."""
    def get(self, request):
        return Response({'regions': get_communes()})


class QuoteShippingView(APIView):
    """
    Cotiza el envío para un conjunto de productos hacia una comuna.
    Si todos los productos son digitales, responde shipping_required=False.
    """
    throttle_scope = 'quote'

    def post(self, request):
        product_ids = request.data.get('product_ids', [])
        commune_name = request.data.get('commune_name')
        commune_id = request.data.get('commune_id')

        if not product_ids:
            return Response({'error': 'Faltan productos'}, status=status.HTTP_400_BAD_REQUEST)

        products = list(Product.objects.filter(id__in=product_ids))
        if not products:
            return Response({'error': 'Productos no encontrados'}, status=status.HTTP_404_NOT_FOUND)

        # Si toda la orden es digital, no hay envío que cotizar.
        if all(p.is_digital for p in products):
            return Response({'shipping_required': False})

        if not commune_name and not commune_id:
            return Response({'error': 'Falta la comuna de destino'}, status=status.HTTP_400_BAD_REQUEST)

        package = build_package_from_products(products)
        # Valor declarado para el seguro de Shipit: el precio real que se cobra
        # (con oferta si corresponde), no el de lista.
        checkout_price = int(sum(p.effective_price for p in products))
        try:
            quotes = get_shipping_quotes(
                commune_name=commune_name, commune_id=commune_id,
                package=package, checkout_price=checkout_price,
            )
        except CotizacionNoDisponible as e:
            # 503 y no 500: no es un error del sitio, es que el servicio de
            # despacho no está respondiendo. El checkout lo muestra tal cual.
            return Response({'error': str(e)},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({
            'shipping_required': True,
            'package': package,
            'quotes': quotes,
        })
