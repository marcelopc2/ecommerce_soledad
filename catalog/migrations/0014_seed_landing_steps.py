import shutil

from django.conf import settings
from django.db import migrations


def seed_steps(apps, schema_editor):
    """Crea los 3 pasos originales de "Cómo funciona" solo si la tabla está
    vacía, copiando las fotos que hoy viven como assets del frontend hacia
    MEDIA_ROOT para que la portada se vea idéntica después de migrar."""
    LandingStep = apps.get_model('catalog', 'LandingStep')
    if LandingStep.objects.exists():
        return

    from catalog.models import DEFAULT_LANDING_STEPS

    origen = settings.BASE_DIR / 'frontend' / 'src' / 'assets' / 'landing'
    destino = settings.MEDIA_ROOT / 'landing_steps'
    destino.mkdir(parents=True, exist_ok=True)

    for i, p in enumerate(DEFAULT_LANDING_STEPS, start=1):
        photo = ''
        archivo = origen / p['photo_asset']
        # Si los assets no están (deploy sin el código del frontend), el paso se
        # crea igual sin foto: la clienta la sube desde el panel.
        if archivo.exists():
            shutil.copyfile(archivo, destino / p['photo_asset'])
            photo = f"landing_steps/{p['photo_asset']}"
        LandingStep.objects.create(
            title=p['title'],
            description=p['description'],
            color=p['color'],
            icon=p['icon'],
            photo=photo,
            order=i,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0013_landingstep'),
    ]

    operations = [
        migrations.RunPython(seed_steps, noop),
    ]
