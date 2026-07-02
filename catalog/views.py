from rest_framework import viewsets
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows products to be viewed.
    Solo listamos los productos activos (is_active=True).
    """
    serializer_class = ProductSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        # Filtramos para que el frontend solo reciba productos habilitados
        return Product.objects.filter(is_active=True).prefetch_related('images', 'category')
