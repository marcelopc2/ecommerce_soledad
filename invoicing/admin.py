import base64
from django.contrib import admin
from django.http import HttpResponse, Http404
from django.urls import path, reverse
from django.utils.html import format_html
from .models import Invoice
from .services import issue_invoice_for_order


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('order_short', 'dte_type', 'folio', 'status', 'issued_at', 'pdf_link', 'short_error')
    list_filter = ('status', 'dte_type')
    search_fields = ('folio', 'order__order_id', 'order__customer_email')
    readonly_fields = ('folio', 'token', 'status', 'error_message', 'created_at', 'issued_at')
    exclude = ('pdf_base64',)
    actions = ('reintentar_emision',)

    @admin.display(description='Orden')
    def order_short(self, obj):
        return str(obj.order.order_id)[:8]

    @admin.display(description='Error')
    def short_error(self, obj):
        return (obj.error_message[:60] + '…') if len(obj.error_message) > 60 else (obj.error_message or '—')

    @admin.display(description='PDF')
    def pdf_link(self, obj):
        if obj.pdf_base64:
            url = reverse('admin:invoicing_invoice_pdf', args=[obj.pk])
            return format_html('<a href="{}">Descargar</a>', url)
        return '—'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/pdf/', self.admin_site.admin_view(self.download_pdf), name='invoicing_invoice_pdf'),
        ]
        return custom + urls

    def download_pdf(self, request, pk):
        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            raise Http404
        if not invoice.pdf_base64:
            raise Http404("La boleta no tiene PDF")
        pdf_bytes = base64.b64decode(invoice.pdf_base64)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"boleta_{invoice.folio or invoice.pk}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @admin.action(description='🧾 Reintentar emisión en OpenFactura')
    def reintentar_emision(self, request, queryset):
        ok, saltadas = 0, 0
        for invoice in queryset:
            if invoice.status == 'ISSUED':
                saltadas += 1
                continue
            result = issue_invoice_for_order(invoice.order)
            if result.status == 'ISSUED':
                ok += 1
            else:
                self.message_user(
                    request,
                    f"Orden {str(invoice.order.order_id)[:8]}: {result.error_message[:120]}",
                    level='error',
                )
        if ok:
            self.message_user(request, f"{ok} boleta(s) emitida(s).", level='success')
        if saltadas:
            self.message_user(request, f"{saltadas} ya estaban emitidas (no se re-emiten).", level='info')
