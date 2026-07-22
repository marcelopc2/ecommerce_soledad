from rest_framework import serializers
from .models import Category, Product, ProductImage, FAQ, Testimonial, LandingVideo, LandingStep

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'is_main']

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description']

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=0, read_only=True)
    features_list = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'category', 'name', 'slug', 'description',
            'price', 'stock', 'is_digital', 'is_active', 'images',
            # oferta / próximamente / compra restringida
            'is_on_sale', 'sale_price', 'effective_price', 'is_coming_soon',
            'requires_login',
            # presentación en la landing
            'show_on_landing', 'landing_order', 'landing_badge',
            'price_note', 'features_list', 'highlight',
        ]

class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'question', 'answer']

class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = ['id', 'name', 'location', 'quote', 'rating']

class LandingVideoSerializer(serializers.ModelSerializer):
    # youtube_id: el front solo necesita el ID para armar el embed; el link
    # completo que pegó la clienta se queda en el panel.
    youtube_id = serializers.CharField(read_only=True)
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = LandingVideo
        fields = ['id', 'title', 'description', 'youtube_id', 'cover_url']

    def get_cover_url(self, obj):
        if not obj.cover:
            return None
        url = obj.cover.url
        # URL absoluta: en desarrollo el front (5173) y el back (8000) están en
        # puertos distintos, así que una ruta relativa apuntaría a Vite.
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url


class LandingStepSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = LandingStep
        fields = ['id', 'title', 'description', 'photo_url', 'color', 'icon']

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class ContactSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=100)
    apellido = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    comentarios = serializers.CharField(max_length=2000, required=False, allow_blank=True)
