"""Baja del sitio viejo las fotos que usan los modelos.

Va aparte del importador a propósito: son dos cosas que fallan por motivos
distintos. Bajar 1.320 archivos depende de la red y del sitio viejo, y puede
quedar a medias; importar depende de la base y tiene que ser todo o nada. Si
estuvieran juntos, un corte de red a mitad de camino dejaría la importación
abortada después de haber trabajado varios minutos.

Es reanudable: lo que ya está bajado no se vuelve a pedir.

    python manage.py bajar_fotos_wordpress --dump ruta.sql --destino carpeta/

Ojo: solo hace GET. No modifica nada en WordPress.
"""
import os
import queue
import threading
import time
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from .importar_wordpress import RE_IMG
from ._wp_dump import una_pasada

#: Suave con el sitio viejo, que sigue atendiendo a las familias de verdad.
HILOS = 4
PAUSA = 0.15


class Command(BaseCommand):
    help = 'Baja las fotos de los pasos desde el WordPress viejo.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True)
        parser.add_argument('--destino', required=True)
        parser.add_argument('--hilos', type=int, default=HILOS)

    def handle(self, *args, **op):
        ruta, destino = op['dump'], op['destino']
        if not os.path.exists(ruta):
            raise CommandError('No encuentro el volcado: %s' % ruta)

        self.stdout.write('Leyendo el volcado para juntar las direcciones...')
        posts, secciones, materiales = {}, {}, []
        adjuntos, portada_de = {}, {}

        def post(f):
            t = f.get('post_type')
            if t in ('stm-courses', 'stm-lessons'):
                posts[f['ID']] = f
            elif t == 'attachment':
                adjuntos[f['ID']] = f.get('guid') or ''

        def postmeta(f):
            if f.get('meta_key') == '_thumbnail_id':
                portada_de[f.get('post_id')] = f.get('meta_value')

        una_pasada(ruta, {
            'wp_posts': post,
            'wp_postmeta': postmeta,
            'wp_stm_lms_curriculum_sections': lambda f: secciones.__setitem__(
                f.get('id'), f.get('course_id')),
            'wp_stm_lms_curriculum_materials': materiales.append,
        })

        cursos = {i for i, p in posts.items()
                  if p.get('post_type') == 'stm-courses' and p.get('post_status') == 'publish'}
        lecciones = {m.get('post_id') for m in materiales
                     if secciones.get(m.get('section_id')) in cursos}

        urls = set()
        for lid in lecciones:
            urls.update(RE_IMG.findall((posts.get(lid) or {}).get('post_content') or ''))
        # Las portadas de los modelos, que no van en el cuerpo sino como adjunto.
        for cid in cursos:
            guid = adjuntos.get(portada_de.get(cid))
            if guid and '/wp-content/uploads/' in guid:
                urls.add(guid)

        os.makedirs(destino, exist_ok=True)
        self.stdout.write('%d archivos que bajar' % len(urls))

        pendientes = queue.Queue()
        for u in sorted(urls):
            pendientes.put(u)

        cerrojo = threading.Lock()
        est = {'ok': 0, 'ya': 0, 'error': 0, 'bytes': 0}
        fallidas = []

        def local(url):
            rel = url.split('/wp-content/uploads/', 1)[-1]
            return os.path.join(destino, rel.replace('/', os.sep))

        def trabajar():
            while True:
                try:
                    url = pendientes.get_nowait()
                except queue.Empty:
                    return
                ruta_f = local(url)
                if os.path.exists(ruta_f) and os.path.getsize(ruta_f) > 0:
                    with cerrojo:
                        est['ya'] += 1
                    continue
                os.makedirs(os.path.dirname(ruta_f), exist_ok=True)
                for intento in range(3):
                    try:
                        pedido = urllib.request.Request(
                            url, headers={'User-Agent': 'IngenioBlocks-Migracion/1.0'})
                        with urllib.request.urlopen(pedido, timeout=45) as r:
                            datos = r.read()
                        # Se escribe a un temporal y recién ahí se renombra: si
                        # el proceso muere a media escritura, no queda un
                        # archivo truncado que luego se dé por bueno.
                        tmp = ruta_f + '.parcial'
                        with open(tmp, 'wb') as f:
                            f.write(datos)
                        os.replace(tmp, ruta_f)
                        with cerrojo:
                            est['ok'] += 1
                            est['bytes'] += len(datos)
                        break
                    except Exception as e:
                        if intento == 2:
                            with cerrojo:
                                est['error'] += 1
                                fallidas.append('%s -> %s' % (url, e))
                        else:
                            time.sleep(1.5 * (intento + 1))
                time.sleep(PAUSA)

        hilos = [threading.Thread(target=trabajar, daemon=True) for _ in range(op['hilos'])]
        for h in hilos:
            h.start()
        while any(h.is_alive() for h in hilos):
            time.sleep(15)
            with cerrojo:
                self.stdout.write('   %d/%d  (%.0f MB)' % (
                    est['ok'] + est['ya'] + est['error'], len(urls), est['bytes'] / 1048576),
                    ending='\n')
                self.stdout.flush()
        for h in hilos:
            h.join()

        self.stdout.write('Bajados %d, ya estaban %d, fallaron %d (%.1f MB)' % (
            est['ok'], est['ya'], est['error'], est['bytes'] / 1048576))
        if fallidas:
            self.stdout.write(self.style.WARNING('\n'.join(fallidas[:10])))
            raise CommandError(
                '%d archivos no se pudieron bajar. Vuelve a correr el comando: '
                'reanuda donde quedó.' % len(fallidas))
        self.stdout.write(self.style.SUCCESS('Listo.'))
