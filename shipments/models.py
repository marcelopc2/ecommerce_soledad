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


class PuntoRetiro(models.Model):
    """La tienda donde se puede retirar en persona. Es una fila única.

    Vive en la base y no en el código porque la dirección, el horario y las
    instrucciones cambian sin aviso -un feriado, un cambio de local- y no puede
    depender de un despliegue. Tampoco puede ser una constante: si la tienda
    cierra un tiempo, la opción tiene que poder apagarse el mismo día.

    Nace APAGADA a propósito: mientras no esté la dirección cargada, ofrecer
    "retiro en tienda" y no decir dónde es peor que no ofrecerlo.
    """

    activo = models.BooleanField(
        default=False,
        help_text='Si está apagado, el retiro en tienda no aparece en el checkout.',
    )
    nombre = models.CharField(
        max_length=120, default='Tienda Ingenio Blocks',
        help_text='Cómo se llama el lugar. Ej: Tienda Ingenio Blocks.',
    )
    direccion = models.CharField(
        max_length=200, blank=True,
        help_text='Calle y número. Ej: Av. Apoquindo 1234.',
    )
    comuna = models.CharField(max_length=120, default='Las Condes')
    ciudad = models.CharField(max_length=120, default='Santiago')
    referencia = models.CharField(
        max_length=200, blank=True,
        help_text='Cómo encontrarlo. Ej: Piso 2, local 15, frente al ascensor.',
    )
    horario = models.TextField(
        blank=True,
        help_text='Cuándo se puede ir a retirar. Ej: Lunes a viernes de 10:00 a 18:00.',
    )
    instrucciones = models.TextField(
        blank=True,
        help_text='Qué tiene que hacer o llevar la persona. Ej: presenta tu número de pedido.',
    )
    mapa_url = models.URLField(
        max_length=500, blank=True,
        help_text='Link a Google Maps, opcional. Aparece como botón "Ver en el mapa".',
    )

    class Meta:
        verbose_name = 'Punto de retiro'
        verbose_name_plural = 'Punto de retiro'

    def __str__(self):
        return f'{self.nombre} · {self.comuna}'

    @classmethod
    def cargar(cls):
        """La fila única, creándola con los valores por omisión si no existe."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def completo(self):
        """¿Tiene lo mínimo para mostrárselo a un cliente?

        Sin dirección, el retiro es una promesa sin lugar. El horario también es
        obligatorio: sin él, la gente llega cuando está cerrado y el reclamo
        llega igual.
        """
        return bool(self.direccion.strip() and self.horario.strip())

    @property
    def disponible(self):
        """True si hoy se puede ofrecer retiro en tienda en el checkout."""
        return self.activo and self.completo

    @property
    def direccion_completa(self):
        partes = [self.direccion, self.comuna, self.ciudad]
        return ', '.join(p for p in partes if p and p.strip())
