from django.db import models
from django.conf import settings
from catalog.models import Product
import uuid

class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pendiente de Pago'),
        ('PAID', 'Pagado'),
        ('FAILED', 'Pago Fallido o Rechazado'),
    )

    # Identificador único para Webpay (buy_order)
    order_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # Usuario (opcional por ahora, lo asociaremos cuando armemos el LMS)
    # user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Productos (simplificado para MVP: asumimos un producto por orden para no complicar el carrito aún, o usamos M2M)
    products = models.ManyToManyField(Product, related_name='orders')
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Transbank Token
    tbk_token = models.CharField(max_length=255, blank=True, null=True)
    
    # Datos de facturación / envío (Básicos)
    customer_email = models.EmailField()

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order_id} - {self.status}"
