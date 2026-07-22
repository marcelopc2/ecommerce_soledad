from django.db import models
from django.conf import settings
from catalog.models import Product
import uuid

class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pendiente de Pago'),
        ('PAID', 'Pagado'),
        ('FAILED', 'Pago Fallido o Rechazado'),
        # No es lo mismo "el pago se rechazó" que "no sabemos si se cobró".
        # Si la red se corta DESPUÉS de que Transbank autorizó, el token es de
        # un solo uso y no hay forma de re-confirmar: marcarla FAILED daba por
        # perdida una compra que sí se cobró. Estas quedan acá para revisarlas
        # a mano contra el portal de Transbank.
        ('REVIEW', 'Requiere revisión manual'),
    )

    # Identificador único para Webpay (buy_order)
    order_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # Usuario (opcional por ahora, lo asociaremos cuando armemos el LMS)
    # user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Productos (simplificado para MVP: asumimos un producto por orden para no complicar el carrito aún, o usamos M2M)
    products = models.ManyToManyField(Product, related_name='orders')
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True,
    )

    # Transbank Token. unique=True porque el commit del pago busca la orden por
    # este campo: dos órdenes con el mismo token reventaban con
    # MultipleObjectsReturned (error 500) justo en el retorno de Transbank.
    # Varios NULL conviven sin problema (es lo que hay mientras no se paga).
    tbk_token = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # Datos de facturación / envío (Básicos)
    customer_email = models.EmailField(db_index=True)

    # Nombres capturados en el checkout. Viven en la Order (y no solo en el
    # Shipment) porque los productos digitales no generan envío, y de ahí se
    # copian a la Membership al aprobarse el pago: el DIPLOMA sale a nombre del
    # alumno, así que ese dato tiene que sobrevivir al proceso de pago.
    customer_name = models.CharField(
        max_length=200, blank=True, help_text="Nombre del apoderado que compra",
    )
    student_name = models.CharField(
        max_length=200, blank=True, help_text="Nombre del niño/a (va en el diploma)",
    )
    customer_phone = models.CharField(max_length=30, blank=True)

    # Indexado porque es el orden por defecto de los listados del panel.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_id} - {self.status}"
