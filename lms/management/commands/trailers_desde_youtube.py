"""Asigna a cada modelo su trailer, sacándolo del canal de YouTube.

Cargar 44 links a mano es una tarde de trabajo y un error de tipeo deja un
reproductor en negro sin que nadie se entere. El canal ya tiene un video por
modelo y los nombres casi calzan, así que se cruzan solos.

Por omisión NO escribe: muestra qué calzaría con qué. Con `--aplicar` guarda.

    python manage.py trailers_desde_youtube
    python manage.py trailers_desde_youtube --aplicar

El cruce es por nombre normalizado (sin tildes, sin mayúsculas, sin palabras
de relleno). Lo que no calza con confianza se informa para revisarlo a mano,
en vez de asignar cualquier cosa: un trailer equivocado es peor que ninguno.
"""
import json
import re
import unicodedata
import urllib.request
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand

from lms.models import Course

CANAL = 'https://www.youtube.com/@IngenioBlocks'
NAVEGADOR = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

#: Los que el parecido no acierta porque en el canal se llaman distinto. Se
#: dejan explícitos y no se fuerza el umbral: bajarlo haría que otros pares
#: parecidos ("Moto de Nieve" / "Moto Vintage") se crucen entre sí.
#:
#: Las claves van YA NORMALIZADAS (sin tildes, sin "de"/"a"/"la"...), porque se
#: consultan después de normalizar el título del curso. Escritas como se leen
#: -"bienvenida a ingenio blocks"- nunca calzaban y la equivalencia no servía
#: de nada, en silencio.
EQUIVALENCIAS = {
    'taladro herramientas': 'taladro electrico',
    'carrusel': 'carrusel sillas voladoras',
    'pozo petrolero': 'plataforma petrolera terrestre',
    'moto vintage': 'moto vintage electrica',
    'elevador tijera': 'elevador tijera',
    'tasitas voladoras': 'tacitas voladoras',
    'bienvenida ingenio blocks': 'bienvenida 1',
}

#: Palabras que no aportan al cruce y solo bajan el parecido.
RELLENO = {'de', 'del', 'la', 'el', 'los', 'las', 'y', 'a', 'en', 'sobre'}


def normalizar(texto):
    """Minúsculas, sin tildes, sin emojis y sin palabras de relleno."""
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t).lower()
    return ' '.join(p for p in t.split() if p not in RELLENO)


def parecido(a, b):
    return SequenceMatcher(None, a, b).ratio()


def videos_del_canal():
    """Todos los videos del canal: {id: título}.

    Se lee la página pública y se pagina con el token de continuación, que es
    la única vía sin pedirle a la clienta una clave de API de Google (un
    trámite en la consola de Google Cloud, con facturación asociada, para algo
    que se corre una vez cada varios meses).
    """
    pedido = urllib.request.Request(CANAL + '/videos', headers={'User-Agent': NAVEGADOR})
    html = urllib.request.urlopen(pedido, timeout=30).read().decode('utf-8', 'replace')

    datos = json.loads(re.search(r'var ytInitialData = (\{.*?\});</script>', html).group(1))
    clave = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html).group(1)
    version = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html).group(1)

    vids = {}
    _cosechar(datos, vids)

    tokens = re.findall(r'"continuationCommand":\{"token":"([^"]+)"', html)
    token = tokens[0] if tokens else None
    for _ in range(10):          # tope de seguridad: el canal no tiene miles
        if not token:
            break
        cuerpo = json.dumps({
            'context': {'client': {'clientName': 'WEB', 'clientVersion': version}},
            'continuation': token,
        }).encode()
        pedido = urllib.request.Request(
            'https://www.youtube.com/youtubei/v1/browse?key=' + clave,
            data=cuerpo,
            headers={'Content-Type': 'application/json', 'User-Agent': NAVEGADOR},
        )
        pagina = json.loads(urllib.request.urlopen(pedido, timeout=30).read())
        antes = len(vids)
        _cosechar(pagina, vids)
        if len(vids) == antes:
            break
        siguientes = re.findall(r'"token":\s*"([^"]+)"', json.dumps(pagina))
        token = siguientes[0] if siguientes else None
    return vids


def _cosechar(obj, vids):
    """Junta {id: título} recorriendo la respuesta de YouTube.

    Se busca la forma en vez de una ruta fija: YouTube cambia la estructura
    cada tanto -ya pasó de `videoRenderer` a `lockupViewModel`- y una ruta
    exacta se rompe en silencio, devolviendo cero videos.
    """
    if isinstance(obj, dict):
        contenido = obj.get('contentId')
        if contenido and 'metadata' in obj and re.fullmatch(r'[\w-]{11}', str(contenido)):
            meta = obj['metadata'].get('lockupMetadataViewModel', {})
            titulo = (meta.get('title') or {}).get('content')
            if titulo:
                vids[contenido] = titulo
        for v in obj.values():
            _cosechar(v, vids)
    elif isinstance(obj, list):
        for v in obj:
            _cosechar(v, vids)


class Command(BaseCommand):
    help = 'Asigna a cada modelo su trailer de YouTube, cruzando por nombre.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Guarda. Sin esto solo muestra qué haría.')
        parser.add_argument('--umbral', type=float, default=0.82,
                            help='Cuánto se tienen que parecer los nombres (0 a 1).')
        parser.add_argument('--pisar', action='store_true',
                            help='También cambia los que ya tienen trailer puesto.')

    def handle(self, *args, **op):
        self.stdout.write('Leyendo el canal...')
        vids = videos_del_canal()
        self.stdout.write('  %d videos en el canal' % len(vids))

        # Índice por nombre normalizado. Si dos videos se llaman igual (el canal
        # tiene dos "Excavadora sobre Oruga") vale el primero: son el mismo
        # modelo resubido, y elegir cualquiera de los dos da lo mismo.
        por_nombre = {}
        for vid, titulo in vids.items():
            por_nombre.setdefault(normalizar(titulo), (vid, titulo))

        calzados, dudosos, sin_video = [], [], []
        for curso in Course.objects.order_by('order'):
            if curso.trailer_url and not op['pisar']:
                continue
            clave = normalizar(curso.title)
            clave = normalizar(EQUIVALENCIAS.get(clave, clave))

            if clave in por_nombre:
                vid, titulo = por_nombre[clave]
                calzados.append((curso, vid, titulo, 1.0))
                continue

            mejor, puntaje = None, 0
            for nombre, (vid, titulo) in por_nombre.items():
                p = parecido(clave, nombre)
                if p > puntaje:
                    mejor, puntaje = (vid, titulo), p
            if mejor and puntaje >= op['umbral']:
                calzados.append((curso, mejor[0], mejor[1], puntaje))
            elif mejor and puntaje >= 0.55:
                dudosos.append((curso, mejor[1], puntaje))
            else:
                sin_video.append(curso)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Calzan (%d)' % len(calzados)))
        for curso, _vid, titulo, p in calzados:
            self.stdout.write('  %-28s -> %-32s %s' % (
                curso.title[:28], titulo[:32], '' if p == 1.0 else '(%.0f%%)' % (p * 100)))

        if dudosos:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Dudosos, NO se asignan (%d)' % len(dudosos)))
            for curso, titulo, p in dudosos:
                self.stdout.write('  %-28s ~ %-32s (%.0f%%)' % (
                    curso.title[:28], titulo[:32], p * 100))

        if sin_video:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Sin video en el canal (%d)' % len(sin_video)))
            for curso in sin_video:
                self.stdout.write('  %s' % curso.title)

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        for curso, vid, _titulo, _p in calzados:
            curso.trailer_url = 'https://www.youtube.com/embed/%s' % vid
            curso.save(update_fields=['trailer_url'])
        self.stdout.write(self.style.SUCCESS(
            '\n%d trailer(s) asignados.' % len(calzados)))
