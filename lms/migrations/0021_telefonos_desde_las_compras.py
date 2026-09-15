"""Rellena el teléfono de cada alumno con el de su última compra.

El campo nace vacío para los 286 alumnos que ya existían, pero el dato SÍ está:
quedó en la orden con que compraron. Sin este relleno, la clienta abriría la
ficha de cualquier alumno migrado y vería el teléfono en blanco, sin manera de
saber que el número existía en otra tabla.

Se toma la orden PAGADA más reciente: si la familia cambió de número entre una
compra y otra, el bueno es el último que usaron.
"""
from django.db import migrations


def rellenar(apps, schema_editor):
    Membership = apps.get_model('lms', 'Membership')

    # Solo las que están vacías: si alguien ya escribió un número a mano antes
    # de que corriera esta migración, no se pisa.
    pendientes = Membership.objects.filter(phone='').prefetch_related('orders')
    a_guardar = []
    for m in pendientes:
        orden = (m.orders.filter(status='PAID')
                 .exclude(customer_phone='')
                 .order_by('-created_at').first())
        if orden:
            m.phone = orden.customer_phone
            a_guardar.append(m)

    Membership.objects.bulk_update(a_guardar, ['phone'], batch_size=200)


def vaciar(apps, schema_editor):
    """Al revertir se vacían todos: no hay forma de distinguir los que rellenó
    esta migración de los que alguien escribió a mano después."""
    apps.get_model('lms', 'Membership').objects.update(phone='')


class Migration(migrations.Migration):
    dependencies = [('lms', '0020_membership_phone')]
    operations = [migrations.RunPython(rellenar, vaciar)]
