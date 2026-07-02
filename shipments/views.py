from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from catalog.models import Product
from .services import get_shipping_quotes, get_communes, build_package_from_products


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
        quotes = get_shipping_quotes(commune_name=commune_name, commune_id=commune_id, package=package)

        return Response({
            'shipping_required': True,
            'package': package,
            'quotes': quotes,
        })
