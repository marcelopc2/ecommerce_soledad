import shutil

from django.conf import settings
from django.db import migrations


def seed_videos(apps, schema_editor):
    """Crea los 3 videos originales de "Sobre el Mundo Ingenio Blocks" solo si la
    tabla está vacía. Copia además las portadas que hoy viven como assets del
    frontend hacia MEDIA_ROOT, para que la portada se vea idéntica después de
    migrar y la clienta solo tenga que reemplazarlas cuando quiera."""
    LandingVideo = apps.get_model('catalog', 'LandingVideo')
    if LandingVideo.objects.exists():
        return

    from catalog.models import DEFAULT_LANDING_VIDEOS

    origen = settings.BASE_DIR / 'frontend' / 'src' / 'assets' / 'landing'
    destino = settings.MEDIA_ROOT / 'landing_videos'
    destino.mkdir(parents=True, exist_ok=True)

    for i, v in enumerate(DEFAULT_LANDING_VIDEOS, start=1):
        cover = ''
        archivo = origen / v['cover_asset']
        # Si los assets no están (ej. deploy sin el código del frontend), el
        # video se crea igual sin portada: la clienta la sube desde el panel.
        if archivo.exists():
            shutil.copyfile(archivo, destino / v['cover_asset'])
            cover = f"landing_videos/{v['cover_asset']}"
        LandingVideo.objects.create(
            title=v['title'],
            description=v['description'],
            youtube_url=v['youtube_url'],
            cover=cover,
            order=i,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_landingvideo'),
    ]

    operations = [
        migrations.RunPython(seed_videos, noop),
    ]
