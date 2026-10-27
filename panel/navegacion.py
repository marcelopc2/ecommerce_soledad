"""El menú del panel: 8 entradas, y las pantallas hermanas como pestañas.

Antes eran 22 entradas en 6 grupos (al estilo WordPress): para encontrar
"Cupones" había que saber que vivía bajo "Tienda". Ahora el menú tiene lo que
se viene a hacer -pedidos, alumnos, productos…- y lo relacionado aparece como
pestañas arriba de cada pantalla (ver partials/subnav.html).

Cada pantalla le dice a la plantilla en qué está con `section`; acá se decide
a qué entrada del menú pertenece. Una `section` que no esté en ninguna lista
simplemente no marca nada: no rompe.
"""
from django.urls import reverse

#: (clave, nombre, ícono, [(section, pestaña, url, solo_superusuario)])
#: La primera pestaña es adonde lleva la entrada del menú.
MENU = [
    ('inicio', 'Inicio', 'bi-house-door-fill', [
        ('dashboard', 'Pendientes y resumen', 'panel:dashboard', False),
        ('visitas', 'Visitas', 'panel:visitas', False),
    ]),
    ('pedidos', 'Pedidos', 'bi-bag-check-fill', [
        ('orders', 'Pedidos', 'panel:orders', False),
        ('suscripciones', 'Suscripciones', 'panel:suscripciones', False),
    ]),
    ('alumnos', 'Alumnos', 'bi-people-fill', [
        ('memberships', 'Alumnos', 'panel:memberships', False),
    ]),
    ('productos', 'Productos', 'bi-box-seam-fill', [
        ('products', 'Productos', 'panel:products', False),
        ('coupons', 'Cupones', 'panel:coupons', False),
    ]),
    ('cursos', 'Cursos', 'bi-mortarboard-fill', [
        ('courses', 'Cursos y diplomas', 'panel:courses', False),
    ]),
    ('portada', 'Portada', 'bi-window-desktop', [
        ('cfg-textos', 'Textos', 'panel:textos_portada', False),
        ('cfg-pasos', 'Cómo funciona', 'panel:cfg_pasos', False),
        ('cfg-testimonios', 'Testimonios', 'panel:cfg_testimonios', False),
        ('cfg-faqs', 'Preguntas frecuentes', 'panel:cfg_faqs', False),
        ('cfg-club', 'Club', 'panel:cfg_club', False),
        ('cfg-concurso', 'Concurso', 'panel:cfg_concurso', False),
        ('cfg-videos', None, 'panel:cfg_videos', False),   # sin pestaña: se llega desde otra pantalla
    ]),
    ('correos', 'Correos', 'bi-envelope-paper-fill', [
        ('correos', 'Correos masivos', 'panel:correos', False),
    ]),
    ('ajustes', 'Ajustes', 'bi-gear-fill', [
        ('interruptores', 'Interruptores', 'panel:interruptores', False),
        ('cfg-aula', 'Entrega semanal', 'panel:cfg_aula', False),
        ('punto-retiro', 'Retiro en tienda', 'panel:punto_retiro', False),
        ('staff', 'Cuentas de gestión', 'panel:staff_users', True),
        ('accesos', 'Registro de accesos', 'panel:accesos', False),
    ]),
]

#: Las 4 que van en la barra de abajo en el celular (la 5ª es "Más").
EN_LA_BARRA_DEL_CELULAR = ('inicio', 'pedidos', 'alumnos', 'productos')


def menu_para(section, usuario):
    """El menú listo para pintar: qué entrada está activa y sus pestañas."""
    salida = []
    for clave, nombre, icono, pestanas in MENU:
        visibles = [
            {'section': s, 'nombre': n, 'url': reverse(u), 'activa': s == section}
            for s, n, u, solo_super in pestanas
            if n and (not solo_super or getattr(usuario, 'is_superuser', False))
        ]
        salida.append({
            'clave': clave, 'nombre': nombre, 'icono': icono,
            'url': visibles[0]['url'],
            'activa': any(s == section for s, _, _, _ in pestanas),
            'pestanas': visibles,
            'en_barra': clave in EN_LA_BARRA_DEL_CELULAR,
        })
    return salida


def pestanas_de(menu):
    """Las pestañas de la entrada activa (solo si hay más de una)."""
    activa = next((m for m in menu if m['activa']), None)
    return activa['pestanas'] if activa and len(activa['pestanas']) > 1 else []
