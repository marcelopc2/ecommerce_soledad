from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    # Congelados a lo que se cobró: no deben editarse desde el admin.
    readonly_fields = ('product', 'name', 'unit_price', 'quantity')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer_email', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_id', 'customer_email')
    readonly_fields = ('order_id', 'tbk_token', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
