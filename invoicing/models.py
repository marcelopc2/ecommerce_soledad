from django.db import models
from payments.models import Order


class Invoice(models.Model):
    """
    Documento tributario electrónico (boleta) emitido vía OpenFactura para una orden pagada.
    La emisión es no-bloqueante: si OpenFactura falla, la orden sigue PAID y la boleta
    queda en ERROR para reintentar desde el admin.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pendiente de emisión'),
        ('ISSUED', 'Emitida'),
        ('ERROR', 'Error al emitir'),
    )

    DTE_BOLETA = 39

    order = models.OneToOneField(Order, related_name='invoice', on_delete=models.CASCADE)

    dte_type = models.IntegerField(default=DTE_BOLETA, help_text="Tipo de DTE (39 = boleta electrónica)")
    folio = models.CharField(max_length=40, blank=True, help_text="Folio asignado por el SII/OpenFactura")
    token = models.CharField(max_length=120, blank=True, help_text="Token del documento en OpenFactura")
    pdf_base64 = models.TextField(blank=True, help_text="PDF de la boleta en base64 (descargable desde el admin)")

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        label = f"Boleta {self.folio}" if self.folio else "Boleta (sin folio)"
        return f"{label} - Orden {str(self.order.order_id)[:8]} - {self.get_status_display()}"
