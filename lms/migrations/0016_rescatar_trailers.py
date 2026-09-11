"""Mueve los trailers curados desde LandingVideo al curso que les corresponde.

La portada mostraba 3 tarjetas fijas con su trailer de YouTube, administradas
en una lista aparte. Ahora los modelos de la portada salen del Aula, así que el
trailer pasa a vivir en el curso. Sin esta migración, esos 3 videos -que ya
estaban grabados, subidos y escritos- se perderían al cambiar de fuente.

El calce es por nombre porque es lo único que comparten las dos tablas, y los
tres coinciden exactamente ('Taladro y Herramientas', 'Caleidoscopio',
'Centrífuga de Ropa'). Si alguno no calza, se deja pasar: es contenido de
marketing, no vale abortar el despliegue por él.
"""
import re

from django.db import migrations

# Copiado acá y no importado de catalog.models a propósito: una migración tiene
# que seguir haciendo lo mismo dentro de diez años, aunque el código de la app
# cambie. Si importara la función y alguien la modificara, esta migración
# empezaría a producir un resultado distinto al que ya se aplicó.
PATRONES = [
    r'(?:youtube\.com/watch\?(?:.*&)?v=)([\w-]{11})',
    r'(?:youtu\.be/)([\w-]{11})',
    r'(?:youtube\.com/embed/)([\w-]{11})',
    r'(?:youtube\.com/shorts/)([\w-]{11})',
    r'^([\w-]{11})$',
]


def a_embed(url):
    """Deja el link listo para el <iframe>.

    Los trailers estaban guardados como link para compartir (youtu.be/…), que
    YouTube se NIEGA a reproducir dentro de otra página: el reproductor queda en
    negro sin ningún error visible. Solo el formato /embed/ funciona.
    """
    url = (url or '').strip()
    for patron in PATRONES:
        m = re.search(patron, url)
        if m:
            return 'https://www.youtube.com/embed/%s' % m.group(1)
    return ''


def traer_trailers(apps, schema_editor):
    LandingVideo = apps.get_model('catalog', 'LandingVideo')
    Course = apps.get_model('lms', 'Course')

    for video in LandingVideo.objects.all():
        if not video.youtube_url:
            continue
        embed = a_embed(video.youtube_url)
        if not embed:
            continue
        curso = Course.objects.filter(title__iexact=video.title.strip()).first()
        if curso and not curso.trailer_url:
            curso.trailer_url = embed
            curso.save(update_fields=['trailer_url'])


def borrar_trailers(apps, schema_editor):
    """Al revertir se vacía el campo: los LandingVideo siguen intactos, así que
    no se pierde nada -la fuente original nunca se tocó-."""
    Course = apps.get_model('lms', 'Course')
    Course.objects.exclude(trailer_url='').update(trailer_url='')


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0015_course_trailer_url'),
        ('catalog', '0019_delete_modeloarmable_delete_seccionmodelos'),
    ]

    operations = [
        migrations.RunPython(traer_trailers, borrar_trailers),
    ]
