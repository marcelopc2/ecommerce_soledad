"""Trae a IngenioBlocks lo que estaba en el WordPress viejo.

Qué trae
--------
- Los 44 modelos publicados (`stm-courses`), con sus pasos.
- Cada paso es una imagen: en WordPress cada "lección" era una foto suelta.
- Las 357 cuentas, con su clave intacta (ver core/hashers.py).
- TODAS las membresías con historial en Paid Memberships Pro, que es el sistema
  que de verdad manda: las 139 suscripciones activas de WooCommerce están todas
  dentro de las 144 de PMPro, más 5 accesos que se dieron a mano. Quien ya no
  está activo entra igual, con su fecha real de vencimiento (queda "Vencida" en
  el panel, no desaparece).
- El nombre del niño/a, para quien lo tenía cargado (un formulario más nuevo lo
  pedía; no todos lo tienen).
- El progreso: qué modelo terminó cada alumno y en qué paso iba, también para
  quien ya no está activo.
- Cada membresía creada por este comando queda marcada `es_legado=True`, para
  distinguirla en el panel de lo que se venda desde el sitio nuevo.

Quién NO entra
---------------
Las cuentas sin ningún registro en PMPro (71 de 357) no reciben membresía: no
hay con qué fecha anclarlas, y case por case, casi ninguna tiene inscripciones
ni pedidos reales. Es la misma regla del sitio nuevo: la membresía se crea
cuando hay algo que respalde el acceso.

Qué NO trae, a propósito
------------------------
- Los 43 cursos en borrador: son los mismos 001-043 duplicados con sufijo
  "- I". Nadie está inscrito en ellos y traerlos dejaría cada modelo repetido.
- Las lecciones sueltas que venían de demo del tema MasterStudy ("Deep
  Learning", "Nvidia New Technologies"), que no pertenecen a ningún modelo.
- Los pedidos: el historial de ventas vive en la contabilidad y en Transbank.
  Traerlos acá crearía boletas que nunca se emitieron desde este sistema.

Cómo se usa
-----------
Por omisión NO escribe nada: muestra lo que haría. Para que escriba de verdad
hay que agregar `--aplicar`.

    python manage.py importar_wordpress --dump ruta.sql --medios carpeta/
    python manage.py importar_wordpress --dump ruta.sql --medios carpeta/ --aplicar
"""
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from lms.models import (
    CategoryCourse, Course, CourseCategory, CourseProgress, Lesson,
    LessonProgress, Membership, MembershipCategory,
)
from django.contrib.auth.models import User

from ._wp_dump import una_pasada

#: El número que encabeza el título en WordPress ("005-Caleidoscopio").
RE_NUMERO = re.compile(r'^(\d{1,3})\s*-\s*(.+)$')
#: La imagen que lleva adentro el cuerpo de una lección.
RE_IMG = re.compile(r'(?:src|href)=["\'](https?://[^"\']+?\.(?:jpe?g|png|webp|gif))["\']', re.I)


def _fecha(texto):
    """Pasa una fecha de MySQL a una con zona horaria. Devuelve None si viene
    en blanco o como '0000-00-00', que es como MySQL guarda "sin fecha"."""
    if not texto or texto.startswith('0000'):
        return None
    try:
        crudo = datetime.strptime(texto[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    return timezone.make_aware(crudo, timezone.get_default_timezone())


def _slug_unico(titulo, usados):
    """Un slug legible y sin repetir. `slugify` deja vacío un título que sea
    puro acento o símbolo, y ahí hay que inventar algo o revienta el unique."""
    base = slugify(unicodedata.normalize('NFKD', titulo)) or 'modelo'
    slug, n = base, 2
    while slug in usados:
        slug = '%s-%d' % (base, n)
        n += 1
    usados.add(slug)
    return slug


class Command(BaseCommand):
    help = 'Trae cursos, alumnos y progreso desde el volcado del WordPress viejo.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True, help='Ruta al archivo .sql')
        parser.add_argument('--medios', required=True,
                            help='Carpeta con las fotos ya descargadas del sitio viejo')
        parser.add_argument('--aplicar', action='store_true',
                            help='Escribe de verdad. Sin esto solo muestra lo que haría.')
        parser.add_argument('--categoria', default='General',
                            help='Categoría donde entran los modelos (debe existir)')
        parser.add_argument('--dias-vigencia', type=int, default=30,
                            help='Cuánto dura la membresía de quien pagaba mes a mes '
                                 'y no tiene fecha de término (por omisión 30 días)')
        parser.add_argument('--sobre-lo-que-hay', action='store_true',
                            help='Deja importar aunque ya existan cursos o alumnos. '
                                 'Ojo: no fusiona, agrega, así que deja todo duplicado.')

    # -- lectura -----------------------------------------------------------

    def _leer(self, ruta):
        """Una sola pasada por los 177 MB, juntando todo lo que hace falta."""
        d = {
            'posts': {}, 'secciones': {}, 'materiales': [], 'usuarios': {},
            'usermeta': {}, 'pmpro': [], 'insc': [], 'lecc_vistas': [],
            'adjuntos': {}, 'portada_de': {},
        }

        def post(f):
            t = f.get('post_type')
            if t in ('stm-courses', 'stm-lessons'):
                d['posts'][f['ID']] = f
            elif t == 'attachment':
                # La portada del curso se guarda aparte, como adjunto: el curso
                # solo apunta a su id con el meta `_thumbnail_id`.
                d['adjuntos'][f['ID']] = f.get('guid') or ''

        def seccion(f):
            d['secciones'][f.get('id')] = f.get('course_id')

        def material(f):
            d['materiales'].append(f)

        def usuario(f):
            d['usuarios'][f['ID']] = f

        def meta(f):
            k = f.get('meta_key')
            if k in ('first_name', 'last_name', 'billing_phone',
                     'billing_first_name', 'billing_last_name',
                     'alumno_nombre', 'alumno_apellido'):
                d['usermeta'].setdefault(f.get('user_id'), {})[k] = f.get('meta_value')

        def pmpro(f):
            # Se juntan TODOS los estados, no solo 'active': un alumno que ya
            # no paga igual tiene que aparecer en el panel como "Vencida", no
            # desaparecer. El filtrado por estado se hace después, agrupando
            # por usuario.
            d['pmpro'].append(f)

        def inscripcion(f):
            d['insc'].append(f)

        def leccion_vista(f):
            d['lecc_vistas'].append(f)

        def postmeta(f):
            if f.get('meta_key') == '_thumbnail_id':
                d['portada_de'][f.get('post_id')] = f.get('meta_value')

        una_pasada(ruta, {
            'wp_posts': post,
            'wp_postmeta': postmeta,
            'wp_stm_lms_curriculum_sections': seccion,
            'wp_stm_lms_curriculum_materials': material,
            'wp_users': usuario,
            'wp_usermeta': meta,
            'wp_pmpro_memberships_users': pmpro,
            'wp_stm_lms_user_courses': inscripcion,
            'wp_stm_lms_user_lessons': leccion_vista,
        })
        return d

    # -- ejecución ---------------------------------------------------------

    def handle(self, *args, **op):
        ruta, medios = op['dump'], op['medios']
        if not os.path.exists(ruta):
            raise CommandError('No encuentro el volcado: %s' % ruta)
        if not os.path.isdir(medios):
            raise CommandError('No encuentro la carpeta de fotos: %s' % medios)

        de_verdad = op['aplicar']

        # El importador agrega, no fusiona: correrlo dos veces, o sobre la base
        # con los cursos de demo, deja cada modelo repetido y con el orden
        # pisado. Se avisa antes de escribir y no después.
        if de_verdad and not op['sobre_lo_que_hay']:
            cursos_ya = Course.objects.count()
            alumnos_ya = Membership.objects.count()
            if cursos_ya or alumnos_ya:
                raise CommandError(
                    'La base no está vacía: ya hay %d curso(s) y %d membresía(s).\n'
                    'Importar encima los duplicaría. Vacíala primero, o usa '
                    '--sobre-lo-que-hay si de verdad quieres agregar.'
                    % (cursos_ya, alumnos_ya))

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Leyendo el volcado (son 177 MB, demora un poco)...'))
        d = self._leer(ruta)

        # --- 1. Los modelos publicados ---------------------------------
        cursos_wp = {
            i: p for i, p in d['posts'].items()
            if p.get('post_type') == 'stm-courses' and p.get('post_status') == 'publish'
        }
        # El orden lo da el número del título, no la fecha: en WordPress se
        # publicaron al revés (el 043 primero), pero un niño los arma del 1 al 43.
        # Lo que no trae número va primero: es el caso de "Bienvenida a Ingenio
        # Blocks", que se ve antes de armar el primer modelo.
        def clave_orden(par):
            m = RE_NUMERO.match((par[1].get('post_title') or '').strip())
            return (1, int(m.group(1))) if m else (0, 0)

        ordenados = sorted(cursos_wp.items(), key=clave_orden)

        # --- 2. Los pasos de cada modelo -------------------------------
        pasos_de = {}
        for m in d['materiales']:
            cid = d['secciones'].get(m.get('section_id'))
            if cid in cursos_wp:
                pasos_de.setdefault(cid, []).append(
                    (int(m.get('order') or 0), m.get('post_id')))
        for v in pasos_de.values():
            v.sort()

        # --- 3. Las cuentas y sus membresías ---------------------------
        # PMPro deja una fila por cada suscripción/cambio de plan, así que un
        # alumno con varias renovaciones aparece varias veces. Se agrupan por
        # usuario para quedarse con UNA membresía por persona:
        #   - inicio  = la fecha más antigua entre TODAS sus filas (activa o
        #     no), porque es cuándo empezó a recibir modelos y es lo que ancla
        #     el goteo semanal, incluso si hoy está vencida y algún día se
        #     reactiva a mano.
        #   - activa  = si tiene AL MENOS una fila con estado 'active' hoy.
        #   - fin     = el vencimiento de esa fila activa: o si no tiene
        #     ninguna activa, el más reciente entre sus vencimientos pasados.
        por_usuario = defaultdict(list)
        for m in d['pmpro']:
            por_usuario[m.get('user_id')].append(m)

        membresias = {}
        for uid, filas_pmpro in por_usuario.items():
            inicios = [f for f in (_fecha(r.get('startdate')) for r in filas_pmpro) if f]
            if not inicios:
                continue
            activa = next((r for r in filas_pmpro if r.get('status') == 'active'), None)
            if activa:
                fin = _fecha(activa.get('enddate'))
            else:
                fines = [f for f in (_fecha(r.get('enddate')) for r in filas_pmpro) if f]
                fin = max(fines) if fines else None
            membresias[uid] = {'inicio': min(inicios), 'fin': fin, 'activa': bool(activa)}

        # Algunas filas de PMPro apuntan a un user_id que ya no existe en
        # wp_users (cuentas de prueba que la clienta borró en su momento, pero
        # cuya membresía quedó huérfana). No hay a quién asignárselas.
        huerfanas = [uid for uid in membresias if uid not in d['usuarios']]
        for uid in huerfanas:
            del membresias[uid]

        self._informe(d, ordenados, pasos_de, membresias, medios, len(huerfanas))

        if not de_verdad:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se escribió nada. Agrega --aplicar para hacerlo de verdad.'))
            return

        with transaction.atomic():
            self._escribir(d, ordenados, pasos_de, membresias, medios, op)

    # -- informe -----------------------------------------------------------

    def _informe(self, d, ordenados, pasos_de, membresias, medios, n_huerfanas):
        faltan = 0
        total_pasos = 0
        for cid, _p in ordenados:
            for _o, lid in pasos_de.get(cid, []):
                total_pasos += 1
                post = d['posts'].get(lid)
                urls = RE_IMG.findall((post or {}).get('post_content') or '')
                if not urls or not os.path.exists(self._ruta_local(urls[0], medios)):
                    faltan += 1

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Lo que se va a crear'))
        self.stdout.write('  Modelos              : %d' % len(ordenados))
        self.stdout.write('  Pasos (con su foto)  : %d' % total_pasos)
        if faltan:
            self.stdout.write(self.style.WARNING('  Pasos SIN foto local : %d' % faltan))
        activas = sum(1 for m in membresias.values() if m['activa'])
        self.stdout.write('  Cuentas              : %d' % len(d['usuarios']))
        self.stdout.write('  Membresías a crear   : %d  (%d activas, %d vencidas)' % (
            len(membresias), activas, len(membresias) - activas))
        if n_huerfanas:
            self.stdout.write(self.style.WARNING(
                '  %d membresía(s) de PMPro apuntan a una cuenta ya borrada, se omiten' % n_huerfanas))
        self.stdout.write('  Inscripciones        : %d' % len(d['insc']))
        self.stdout.write('  Pasos ya vistos      : %d' % len(d['lecc_vistas']))

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Los primeros modelos, en el orden que quedarán'))
        for i, (cid, p) in enumerate(ordenados[:5], 1):
            m = RE_NUMERO.match((p.get('post_title') or '').strip())
            titulo = m.group(2) if m else p.get('post_title')
            self.stdout.write('  %2d. %-42s %d pasos' % (i, titulo, len(pasos_de.get(cid, []))))
        if len(ordenados) > 5:
            self.stdout.write('      ... y %d más' % (len(ordenados) - 5))

    # -- escritura ---------------------------------------------------------

    def _ruta_local(self, url, medios):
        rel = url.split('/wp-content/uploads/', 1)[-1]
        return os.path.join(medios, rel.replace('/', os.sep))

    def _escribir(self, d, ordenados, pasos_de, membresias, medios, op):
        try:
            categoria = CourseCategory.objects.get(nombre=op['categoria'])
        except CourseCategory.DoesNotExist:
            raise CommandError(
                'No existe la categoría "%s". Créala primero desde el panel.' % op['categoria'])

        self.stdout.write(self.style.MIGRATE_HEADING('\nEscribiendo...'))

        # --- modelos y pasos ---
        usados = set(Course.objects.values_list('slug', flat=True))
        curso_de_wp = {}
        leccion_de_wp = {}
        sin_foto = 0

        for pos, (cid, p) in enumerate(ordenados, 1):
            m = RE_NUMERO.match((p.get('post_title') or '').strip())
            titulo = (m.group(2) if m else p.get('post_title') or 'Modelo').strip()
            curso = Course(
                title=titulo[:200],
                slug=_slug_unico(titulo, usados),
                description='',
                order=pos,
                is_active=True,
            )
            portada = d['adjuntos'].get(d['portada_de'].get(cid))
            if portada:
                local = self._ruta_local(portada, medios)
                if os.path.exists(local):
                    with open(local, 'rb') as f:
                        curso.image_file.save(
                            os.path.basename(local), ContentFile(f.read()), save=False)
            curso.save()
            curso_de_wp[cid] = curso
            # Sin esta fila el modelo existe pero no se lo entrega a nadie: el
            # acceso del alumno se calcula desde la categoría, no desde Course.
            CategoryCourse.objects.create(categoria=categoria, curso=curso, orden=pos)

            for orden, lid in pasos_de.get(cid, []):
                post = d['posts'].get(lid)
                if not post:
                    continue
                urls = RE_IMG.findall(post.get('post_content') or '')
                local = self._ruta_local(urls[0], medios) if urls else None
                leccion = Lesson(
                    course=curso,
                    title=(post.get('post_title') or 'Paso')[:200],
                    order=orden or 1,
                    lesson_type='IMAGE',
                )
                if local and os.path.exists(local):
                    with open(local, 'rb') as f:
                        leccion.image_file.save(
                            os.path.basename(local), ContentFile(f.read()), save=False)
                else:
                    sin_foto += 1
                leccion.save()
                leccion_de_wp[lid] = leccion

        self.stdout.write('  %d modelos y %d pasos creados%s' % (
            len(curso_de_wp), len(leccion_de_wp),
            (' (%d sin foto)' % sin_foto) if sin_foto else ''))

        # --- cuentas ---
        ahora = timezone.now()
        user_de_wp = {}
        reusadas = []
        ya_estaban = {u.username.lower(): u for u in User.objects.all()}
        for uid, u in d['usuarios'].items():
            correo = (u.get('user_email') or '').strip().lower()
            if not correo:
                continue

            # La clienta y su equipo ya tienen cuenta acá, y también aparecen en
            # el WordPress viejo. Se reutiliza la que existe y NO se le toca
            # nada: pisarle la clave o los permisos la dejaría fuera del panel.
            existente = ya_estaban.get(correo[:150].lower())
            if existente:
                user_de_wp[uid] = existente
                reusadas.append(correo)
                continue

            meta = d['usermeta'].get(uid, {})
            nombre = meta.get('first_name') or meta.get('billing_first_name') or ''
            apellido = meta.get('last_name') or meta.get('billing_last_name') or ''
            django_user = User.objects.create(
                username=correo[:150],
                email=correo,
                first_name=nombre[:150],
                last_name=apellido[:150],
                is_active=True,
                date_joined=_fecha(u.get('user_registered')) or ahora,
                # El hasher lo reconoce por este prefijo y lo reescribe con
                # PBKDF2 la primera vez que la persona entra bien.
                password='wordpress$' + (u.get('user_pass') or ''),
            )
            ya_estaban[correo[:150].lower()] = django_user
            user_de_wp[uid] = django_user
        self.stdout.write('  %d cuentas creadas' % (len(user_de_wp) - len(reusadas)))
        if reusadas:
            self.stdout.write('  %d ya existían y se dejaron intactas: %s' % (
                len(reusadas), ', '.join(reusadas[:5])))

        # --- membresías ---
        creadas = activas = vencidas = 0
        for uid, info in membresias.items():
            usuario = user_de_wp.get(uid)
            if not usuario:
                continue
            inicio = info['inicio'] or ahora
            if info['activa']:
                # Quien pagaba mes a mes no tiene fecha de término en PMPro: se
                # le da la vigencia por omisión y su próximo pago la extiende,
                # igual que a cualquier cliente nuevo.
                fin = info['fin'] or (ahora + timedelta(days=op['dias_vigencia']))
            else:
                # Ya no paga: se respeta su fecha real de término (siempre la
                # trae PMPro para estos casos), y por eso el panel la muestra
                # "Vencida" en vez de ocultarla.
                fin = info['fin'] or inicio

            meta = d['usermeta'].get(uid, {})
            nombre_alumno = ('%s %s' % (
                meta.get('alumno_nombre') or '', meta.get('alumno_apellido') or '')).strip()

            # Membership es uno-a-uno: si la cuenta se reutilizó y ya tenía una,
            # se respeta la que hay en vez de reventar a mitad de la carga.
            membresia, nueva = Membership.objects.get_or_create(
                user=usuario,
                defaults={
                    'expires_at': fin,
                    'parent_name': ('%s %s' % (usuario.first_name, usuario.last_name)).strip()[:200],
                    'student_name': nombre_alumno[:200],
                    'es_legado': True,
                },
            )
            if not nueva:
                continue
            # `created_at` es `auto_now_add`: Django lo pisa con el instante en
            # que se ejecuta este comando, no con la fecha real de alta. Sin
            # este ajuste, el panel mostraría "Inicio: hoy" para 286 familias
            # que en realidad llevan meses. `.update()` no dispara ese
            # auto_now_add (solo pasa en `.save()`), así que sirve para
            # corregirlo después de crear la fila.
            Membership.objects.filter(pk=membresia.pk).update(created_at=inicio)
            # `obtenida_en` es lo que ancla el goteo semanal. Va la fecha
            # original: si fuera la de hoy, una familia que lleva un año
            # pagando volvería a la semana 1 y perdería los modelos que ya tenía.
            # Se guarda también para quien ya no está activo: si algún día se
            # reactiva a mano, retoma donde iba en vez de partir de cero.
            MembershipCategory.objects.create(
                membership=membresia, categoria=categoria, obtenida_en=inicio,
            )
            creadas += 1
            if info['activa']:
                activas += 1
            else:
                vencidas += 1
        self.stdout.write('  %d membresías creadas  (%d activas, %d vencidas)' % (
            creadas, activas, vencidas))

        # --- progreso ---
        membresia_de = {mm.user_id: mm for mm in Membership.objects.all()}
        hechos = 0
        for r in d['insc']:
            try:
                pct = float(r.get('progress_percent') or 0)
            except ValueError:
                pct = 0
            if pct < 100:
                continue
            usuario = user_de_wp.get(r.get('user_id'))
            curso = curso_de_wp.get(r.get('course_id'))
            mem = membresia_de.get(usuario.id) if usuario else None
            if not (curso and mem):
                continue
            _o, nuevo = CourseProgress.objects.get_or_create(
                membership=mem, course=curso,
                defaults={'completed_at': _fecha(r.get('end_time')) or ahora},
            )
            hechos += 1 if nuevo else 0

        pasos_ok = 0
        for r in d['lecc_vistas']:
            usuario = user_de_wp.get(r.get('user_id'))
            leccion = leccion_de_wp.get(r.get('lesson_id'))
            mem = membresia_de.get(usuario.id) if usuario else None
            if not (leccion and mem):
                continue
            _o, nuevo = LessonProgress.objects.get_or_create(
                membership=mem, lesson=leccion,
                defaults={'completed_at': _fecha(r.get('end_time')) or ahora},
            )
            pasos_ok += 1 if nuevo else 0

        self.stdout.write('  %d modelos terminados y %d pasos marcados' % (hechos, pasos_ok))
        self.stdout.write(self.style.SUCCESS('\nListo.'))
