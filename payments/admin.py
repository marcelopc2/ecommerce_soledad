from django.contrib import admin
from .models import Order

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer_email', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_id', 'customer_email')
    readonly_fields = ('order_id', 'tbk_token', 'created_at', 'updated_at')
