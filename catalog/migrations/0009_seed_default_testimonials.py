from django.db import migrations

def seed_testimonials(apps, schema_editor):
    """Crea los 4 testimonios por defecto solo si la tabla está vacía, para no
    duplicar si esta migración corre más de una vez en un mismo entorno."""
    Testimonial = apps.get_model('catalog', 'Testimonial')
    if Testimonial.objects.exists():
        return
    from catalog.models import DEFAULT_TESTIMONIALS
    Testimonial.objects.bulk_create([
        Testimonial(
            name=t['name'], location=t['location'], quote=t['quote'],
            rating=t['rating'], order=i,
        )
        for i, t in enumerate(DEFAULT_TESTIMONIALS, start=1)
    ])

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_testimonial'),
    ]

    operations = [
        migrations.RunPython(seed_testimonials, noop),
    ]
