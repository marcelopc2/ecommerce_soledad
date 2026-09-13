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

    # Cupón usado, si hubo. PROTECT y no SET_NULL: si se borrara el cupón, las
    # ventas quedarían sin saber con qué descuento se vendieron. Un cupón usado
    # se desactiva, no se borra (mismo criterio que los productos vendidos).
    coupon = models.ForeignKey(
        'Coupon', related_name='orders', on_delete=models.PROTECT,
        null=True, blank=True,
    )
    #: Pesos descontados por el cupón. Se guarda aparte del total porque el
    #: total ya viene rebajado y, sin esto, no habría cómo saber cuánto se
    #: regaló ni reconstruir el precio de lista.
    discount_amount = models.PositiveIntegerField(default=0)

    # Indexado porque es el orden por defecto de los listados del panel.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_id} - {self.status}"



class Coupon(models.Model):
    """Un cupón de descuento, del tipo que se reparte en un CyberMonday.

    Las reglas que se pueden configurar (fechas, tope de usos, un uso por
    correo, compra mínima) están todas acá; quién decide si se puede usar en
    una compra concreta es payments/coupons.py.

    El descuento se aplica SOLO a los productos, nunca al despacho.
    """

    PORCENTAJE = 'PERCENT'
    MONTO = 'AMOUNT'
    TIPOS = (
        (PORCENTAJE, 'Porcentaje de descuento'),
        (MONTO, 'Monto fijo en pesos'),
    )

    # Se guarda siempre en mayúsculas (ver save): el código que escribe el
    # cliente se compara normalizado, así "cyber25" y "CYBER25" son el mismo.
    code = models.CharField(
        max_length=30, unique=True, db_index=True,
        help_text='Lo que escribe el cliente al pagar. Ej: CYBER2026',
    )
    description = models.CharField(
        max_length=200, blank=True,
        help_text='Nota interna para acordarse de para qué era. No la ve el cliente.',
    )

    discount_type = models.CharField(max_length=10, choices=TIPOS, default=PORCENTAJE)
    value = models.PositiveIntegerField(
        help_text='Si es porcentaje, de 1 a 100. Si es monto fijo, los pesos a descontar.',
    )

    min_purchase = models.PositiveIntegerField(
        default=0, help_text='Compra mínima para poder usarlo. 0 = sin mínimo.',
    )
    starts_at = models.DateTimeField(
        null=True, blank=True, help_text='Desde cuándo sirve. Vacío = desde ya.',
    )
    ends_at = models.DateTimeField(
        null=True, blank=True, help_text='Hasta cuándo sirve. Vacío = sin vencimiento.',
    )
    max_uses = models.PositiveIntegerField(
        null=True, blank=True, help_text='Tope de compras que pueden usarlo. Vacío = sin tope.',
    )
    once_per_email = models.BooleanField(
        default=False, help_text='Cada correo puede usarlo una sola vez.',
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        return super().save(*args, **kwargs)

    @property
    def usos(self):
        """Cuántas compras PAGADAS lo usaron.

        Se cuenta sobre las pagadas y no con un contador propio a propósito: un
        contador que sube al crear la orden se queda alto para siempre cuando la
        persona abandona el pago a medio camino, y termina agotando un cupón que
        en realidad nadie usó. El costo es que dos compras simultáneas podrían
        pasarse del tope por una; a la escala de esta tienda eso no pasa, y
        regalar un descuento de más es mejor que no vender.

        Si la consulta ya vino con `usos_pagados` anotado (lo hace la lista del
        panel), se usa eso: sin el atajo, pintar 20 filas eran 20 consultas
        más las que gatillan `agotado` y `vigente` sobre cada una.
        """
        anotado = getattr(self, 'usos_pagados', None)
        if anotado is not None:
            return anotado
        return self.orders.filter(status='PAID').count()

    def descuento_sobre(self, subtotal):
        """Cuántos pesos descuenta sobre ese subtotal de productos.

        Nunca más que el subtotal: un cupón de $10.000 sobre una compra de
        $6.000 descuenta $6.000, no deja la orden en negativo.
        """
        subtotal = int(subtotal)
        if subtotal <= 0:
            return 0
        if self.discount_type == self.PORCENTAJE:
            bruto = subtotal * self.value // 100
        else:
            bruto = self.value
        return max(0, min(int(bruto), subtotal))

    @property
    def etiqueta(self):
        """Cómo se nombra el descuento en pantalla. Ej: "25%" o "$5.000"."""
        if self.discount_type == self.PORCENTAJE:
            return f'{self.value}%'
        return '${:,.0f}'.format(self.value).replace(',', '.')

    @property
    def vencido(self):
        from django.utils import timezone
        return bool(self.ends_at and timezone.now() > self.ends_at)

    @property
    def agotado(self):
        return self.max_uses is not None and self.usos >= self.max_uses

    @property
    def por_empezar(self):
        from django.utils import timezone
        return bool(self.starts_at and timezone.now() < self.starts_at)

    @property
    def vigente(self):
        """True si hoy un cliente podría usarlo (sin mirar su compra)."""
        return self.is_active and not self.vencido and not self.agotado and not self.por_empezar


class OrderItem(models.Model):
    """Una línea de la orden, con el precio y el nombre CONGELADOS al momento de
    la compra.

    Existe por dos motivos:

    1. La boleta y el historial deben reflejar lo que se cobró de verdad, no el
       precio actual del producto. Si mañana sube el precio, una boleta vieja
       re-emitida salía con el valor nuevo (leía Product.price en vivo).

    2. on_delete=PROTECT sobre el producto: mientras exista una venta de un
       producto, no se puede borrar ni desde el panel ni desde el admin de
       Django. Antes (M2M pelado) borrar un producto vaciaba en silencio los
       pedidos históricos que lo contenían.

    El M2M Order.products se conserva para lo que solo necesita la identidad del
    producto (otorgar cursos en el LMS, el panel). Esta tabla es la fuente de
    verdad de la plata.
    """
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.PROTECT)
    name = models.CharField(max_length=200, help_text="Nombre del producto al momento de la compra")
    unit_price = models.DecimalField(max_digits=10, decimal_places=0, help_text="Precio cobrado por unidad")
    quantity = models.PositiveIntegerField(default=1)

    @property
    def subtotal(self):
        return int(self.unit_price) * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.name} (${self.unit_price})"
