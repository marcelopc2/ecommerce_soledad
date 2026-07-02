from django.db import models
from payments.models import Order


class Shipment(models.Model):
    """
    Envío asociado a una orden pagada. Guarda el destino, la cotización elegida
    (que se suma al total de la orden) y, tras el despacho, el tracking + etiqueta
    que devuelve Shipit. Se crea solo si la orden tiene al menos un producto físico.
    """
    STATUS_CHOICES = (
        ('PENDING_DISPATCH', 'Pendiente de despacho'),
        ('CREATED', 'Envío creado (etiqueta generada)'),
        ('IN_TRANSIT', 'En tránsito'),
        ('DELIVERED', 'Entregado'),
        ('ERROR', 'Error al crear en Shipit'),
    )

    order = models.OneToOneField(Order, related_name='shipment', on_delete=models.CASCADE)

    # --- Destinatario ---
    recipient_name = models.CharField(max_length=200)
    recipient_phone = models.CharField(max_length=30)
    recipient_email = models.EmailField(blank=True)

    # --- Destino ---
    region = models.CharField(max_length=120)
    commune = models.CharField(max_length=120)
    commune_id = models.IntegerField(null=True, blank=True, help_text="ID interno de Shipit")
    address_street = models.CharField(max_length=255)
    address_number = models.CharField(max_length=30)
    address_detail = models.CharField(max_length=255, blank=True, help_text="Depto/oficina/referencia")

    # --- Cotización elegida (se guarda al checkout) ---
    courier = models.CharField(max_length=80)
    service_name = models.CharField(max_length=120, blank=True)
    shipping_cost = models.IntegerField(default=0, help_text="CLP; se suma a Order.total_amount")
    estimated_days = models.CharField(max_length=120, blank=True)

    # --- Snapshot del paquete (al cotizar) ---
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    width_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    length_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)

    # --- Despacho (lo llena la clienta desde el admin) ---
    shipit_reference = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    label_url = models.URLField(max_length=500, blank=True, help_text="PDF de la etiqueta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_DISPATCH')

    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Envío {self.order.order_id} - {self.get_status_display()}"
