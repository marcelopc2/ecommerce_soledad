from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import Shipment
from .services import enviar_pedido_a_shipit


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

    @admin.action(description='Mandar a Ventas de Shipit')
    def crear_envio_en_shipit(self, request, queryset):
        """Lo mismo que el botón del panel: manda a Ventas de Shipit (nunca
        crea el envío directo, que agenda el retiro del courier)."""
        mandados = errores = 0
        for shipment in queryset.select_related('order'):
            enviar_pedido_a_shipit(shipment.order)
            shipment.refresh_from_db()
            if shipment.status == 'ERROR':
                errores += 1
                self.message_user(request, f"Orden {str(shipment.order.order_id)[:8]}: {shipment.error_shipit}",
                                  level='error')
            elif shipment.shipit_reference:
                mandados += 1
        if mandados:
            self.message_user(request, f"{mandados} pedido(s) en Ventas de Shipit.", level='success')
