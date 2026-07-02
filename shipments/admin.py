from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import Shipment
from .services import create_shipit_shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'order_short', 'recipient_name', 'commune', 'courier',
        'shipping_cost', 'status', 'tracking_number', 'label_link',
    )
    list_filter = ('status', 'courier')
    search_fields = ('tracking_number', 'recipient_email', 'recipient_name', 'order__order_id')
    readonly_fields = ('shipit_reference', 'tracking_number', 'label_url', 'created_at', 'dispatched_at')
    actions = ('crear_envio_en_shipit',)

    @admin.display(description='Orden')
    def order_short(self, obj):
        return str(obj.order.order_id)[:8]

    @admin.display(description='Etiqueta')
    def label_link(self, obj):
        if obj.label_url:
            return format_html('<a href="{}" target="_blank">Descargar</a>', obj.label_url)
        return '—'

    @admin.action(description='🏷️ Crear envío en Shipit (genera etiqueta + tracking)')
    def crear_envio_en_shipit(self, request, queryset):
        creados, saltados, errores = 0, 0, 0
        for shipment in queryset:
            # Idempotencia: no recrear envíos ya generados.
            if shipment.status == 'CREATED' or shipment.shipit_reference:
                saltados += 1
                continue
            # Solo órdenes pagadas.
            if shipment.order.status != 'PAID':
                self.message_user(
                    request,
                    f"Orden {str(shipment.order.order_id)[:8]}: no está pagada, se omite.",
                    level='warning',
                )
                saltados += 1
                continue
            try:
                result = create_shipit_shipment(shipment)
                shipment.shipit_reference = result.get('reference', '')
                shipment.tracking_number = result.get('tracking_number', '')
                shipment.label_url = result.get('label_url', '')
                shipment.status = 'CREATED'
                shipment.dispatched_at = timezone.now()
                shipment.save()
                creados += 1
            except Exception as e:
                shipment.status = 'ERROR'
                shipment.save()
                errores += 1
                self.message_user(
                    request,
                    f"Orden {str(shipment.order.order_id)[:8]}: error creando envío en Shipit → {e}",
                    level='error',
                )

        if creados:
            self.message_user(request, f"{creados} envío(s) creado(s) en Shipit.", level='success')
        if saltados:
            self.message_user(request, f"{saltados} envío(s) omitido(s) (ya creados o sin pagar).", level='info')
