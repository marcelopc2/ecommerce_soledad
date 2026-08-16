import logging
from django.conf import settings
from core.emails import enviar_email
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import (
    Category, Product, FAQ, Testimonial, LandingVideo, LandingStep,
    SeccionConcurso, GanadorConcurso,
    ModeloArmable, SeccionModelos,
)
from .serializers import (
    CategorySerializer, ProductSerializer, FAQSerializer, TestimonialSerializer,
    ContactSerializer, LandingVideoSerializer, LandingStepSerializer,
    SeccionConcursoSerializer, GanadorConcursoSerializer,
    ModeloArmableSerializer, SeccionModelosSerializer,
)

log = logging.getLogger(__name__)

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
        # Filtramos para que el frontend solo reciba productos habilitados.
        # category es ForeignKey → select_related (un JOIN); images es reversa
        # → prefetch_related. Tenerlos juntos en prefetch gastaba una consulta
        # extra por cada listado.
        return (Product.objects.filter(is_active=True)
                .select_related('category')
                .prefetch_related('images'))

class FAQViewSet(viewsets.ReadOnlyModelViewSet):
    """Preguntas frecuentes activas, en el orden que fijó el panel."""
    serializer_class = FAQSerializer

    def get_queryset(self):
        return FAQ.objects.filter(is_active=True)

class TestimonialViewSet(viewsets.ReadOnlyModelViewSet):
    """Testimonios activos, en el orden que fijó el panel."""
    serializer_class = TestimonialSerializer

    def get_queryset(self):
        return Testimonial.objects.filter(is_active=True)

class LandingVideoViewSet(viewsets.ReadOnlyModelViewSet):
    """Videos activos de "Sobre el Mundo Ingenio Blocks", en el orden del panel."""
    serializer_class = LandingVideoSerializer

    def get_queryset(self):
        return LandingVideo.objects.filter(is_active=True)


class LandingStepViewSet(viewsets.ReadOnlyModelViewSet):
    """Pasos activos de "Cómo funciona", en el orden del panel."""
    serializer_class = LandingStepSerializer

    def get_queryset(self):
        return LandingStep.objects.filter(is_active=True)


class ConcursoView(APIView):
    """Estado y contenido de la franja del concurso. Va en un solo endpoint
    (y no en dos) porque la landing necesita saber el estado ANTES de decidir
    qué pedir: así se resuelve con una sola llamada."""
    permission_classes = [AllowAny]

    def get(self, request):
        seccion = SeccionConcurso.obtener()
        datos = SeccionConcursoSerializer(seccion, context={'request': request}).data
        # Los ganadores solo se envían si de verdad se van a mostrar: no tiene
        # sentido publicar nombres de menores mientras la sección está oculta
        # o en convocatoria.
        if seccion.estado == SeccionConcurso.GANADORES:
            ganadores = GanadorConcurso.objects.filter(is_active=True)
            datos['ganadores'] = GanadorConcursoSerializer(
                ganadores, many=True, context={'request': request},
            ).data
        else:
            datos['ganadores'] = []
        return Response(datos)


class ContactView(APIView):
    """Formulario de contacto de la landing: envía el mensaje por correo a
    settings.CONTACT_EMAIL en vez de depender de mailto: (que requiere un
    cliente de correo configurado en el navegador del visitante)."""
    permission_classes = [AllowAny]
    throttle_scope = 'contact'  # anti spam de correos

    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        nombre_completo = f"{data['nombre']} {data.get('apellido', '')}".strip()

        try:
            # fail_silently=False acá a propósito: a diferencia de los correos
            # post-compra, si este no sale el mensaje se pierde sin que nadie
            # se entere, así que el visitante tiene que saberlo para reintentar.
            enviar_email(
                'contacto_interno',
                asunto=f'Contacto desde la web · {nombre_completo}',
                destinatarios=[settings.CONTACT_EMAIL],
                contexto={
                    'nombre': nombre_completo,
                    'email': data['email'],
                    'telefono': data.get('telefono'),
                    'comentarios': data.get('comentarios'),
                },
                reply_to=[data['email']],   # responder le llega a quien escribió
                fail_silently=False,
            )
        except Exception:
            # Un mensaje de contacto perdido es un cliente perdido: queda en el
            # log con el correo de quien escribió para poder responderle igual.
            log.exception('No se pudo enviar el mensaje de contacto de %s', data['email'])
            return Response(
                {'error': 'No pudimos enviar tu mensaje. Intenta nuevamente en unos minutos.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({'ok': True})


class ModelosView(APIView):
    """La vitrina de modelos: los ajustes de la página más su lista.

    Un solo endpoint y no dos, por lo mismo que el concurso: el menú de la
    landing necesita saber si la página está visible ANTES de decidir si muestra
    el enlace, y así se resuelve con una sola llamada.

    Con la página apagada NO se envían los modelos. Si se enviaran, apagarla
    sería solo esconder el enlace: la lista seguiría a la vista de cualquiera
    que mirara la respuesta de la API.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        seccion = SeccionModelos.obtener()
        datos = SeccionModelosSerializer(seccion).data
        datos['modelos'] = (
            ModeloArmableSerializer(
                ModeloArmable.objects.filter(is_active=True), many=True,
                context={'request': request},
            ).data
            if seccion.visible else []
        )
        return Response(datos)
