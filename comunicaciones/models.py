import hashlib

from django.conf import settings
from django.db import models

from .preferencias import AULA, NOVEDADES, normalizar


class BajaDeCorreo(models.Model):
    """Alguien pidió no recibir más una categoría de correos.

    Va por dirección y SIN llave foránea al usuario, a propósito: la importación
    desde WordPress borra y recrea a los alumnos, y la baja tiene que
    sobrevivirle. Ver comunicaciones/preferencias.py.
    """
    CATEGORIAS = [
        (NOVEDADES, 'Novedades'),
        (AULA, 'Avisos del Aula'),
    ]
    ORIGENES = [
        ('enlace', 'Desde el enlace del correo'),
        ('un_clic', 'Con el botón de baja de su correo'),
        ('cuenta', 'Desde su cuenta'),
    ]
    email = models.EmailField()
    categoria = models.CharField(max_length=20, choices=CATEGORIAS)
    origen = models.CharField(max_length=20, choices=ORIGENES, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('email', 'categoria')]
        ordering = ['-creada_en']
        verbose_name = 'baja de correo'
        verbose_name_plural = 'bajas de correo'

    def save(self, *args, **kwargs):
        self.email = normalizar(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.email} · {self.get_categoria_display()}'


class EnvioMasivo(models.Model):
    """Un correo masivo, desde que se redacta hasta que termina de salir.

    Se guarda todo lo que se mandó y a quién, para poder responder después
    "¿le llegó a tal persona?" sin adivinar.
    """
    BORRADOR = 'BORRADOR'
    EN_COLA = 'EN_COLA'
    TERMINADO = 'TERMINADO'
    CANCELADO = 'CANCELADO'
    ESTADOS = [
        (BORRADOR, 'Borrador'),
        (EN_COLA, 'Enviándose'),
        (TERMINADO, 'Enviado'),
        (CANCELADO, 'Cancelado'),
    ]

    TODOS = 'TODOS'
    VIGENTES = 'VIGENTES'
    AUDIENCIAS = [
        (TODOS, 'Todos los clientes'),
        (VIGENTES, 'Solo con membresía vigente'),
    ]

    asunto = models.CharField(max_length=150)
    cuerpo = models.TextField(
        help_text='Separa los párrafos con una línea en blanco. Las direcciones '
                  'web se vuelven enlaces solas.')
    boton_texto = models.CharField(
        'Texto del botón', max_length=40, blank=True,
        help_text='Opcional. Ej: "Conoce la nueva página".')
    boton_url = models.URLField(
        'Dirección del botón', blank=True,
        help_text='A dónde lleva el botón. Tiene que empezar con https://')
    audiencia = models.CharField(max_length=10, choices=AUDIENCIAS, default=TODOS)

    estado = models.CharField(max_length=10, choices=ESTADOS, default=BORRADOR)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='envios_masivos')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    # La prueba vale para ESTE contenido: se guarda la huella de lo que se
    # probó, y si después se cambia una coma, hay que volver a probar.
    prueba_enviada_en = models.DateTimeField(null=True, blank=True)
    prueba_huella = models.CharField(max_length=64, blank=True)

    encolado_en = models.DateTimeField(null=True, blank=True)
    terminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'correo masivo'
        verbose_name_plural = 'correos masivos'

    def __str__(self):
        return self.asunto

    def huella(self):
        """Resumen de lo que ve el destinatario. La audiencia no entra: cambiar
        a quién se manda no cambia lo que se probó."""
        contenido = '\x1f'.join([self.asunto, self.cuerpo, self.boton_texto, self.boton_url])
        return hashlib.sha256(contenido.encode('utf-8')).hexdigest()

    @property
    def prueba_al_dia(self):
        return bool(self.prueba_huella) and self.prueba_huella == self.huella()

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    def parrafos(self):
        return [p.strip() for p in self.cuerpo.replace('\r\n', '\n').split('\n\n') if p.strip()]

    def contadores(self):
        cuenta = {e: 0 for e, _ in DestinatarioMasivo.ESTADOS}
        for fila in self.destinatarios.values('estado').annotate(n=models.Count('id')):
            cuenta[fila['estado']] = fila['n']
        cuenta['total'] = sum(v for k, v in cuenta.items() if k != 'total')
        cuenta['procesados'] = cuenta['total'] - cuenta[DestinatarioMasivo.PENDIENTE] \
            - cuenta[DestinatarioMasivo.ENVIANDO]
        cuenta['porcentaje'] = round(100 * cuenta['procesados'] / cuenta['total']) if cuenta['total'] else 0
        return cuenta


class DestinatarioMasivo(models.Model):
    """Una persona dentro de un envío masivo, y qué pasó con su correo."""
    PENDIENTE = 'PENDIENTE'
    ENVIANDO = 'ENVIANDO'
    ENVIADO = 'ENVIADO'
    FALLIDO = 'FALLIDO'
    OMITIDO = 'OMITIDO'
    ESTADOS = [
        (PENDIENTE, 'Pendiente'),
        (ENVIANDO, 'Enviándose'),
        (ENVIADO, 'Enviado'),
        (FALLIDO, 'Falló'),
        (OMITIDO, 'Omitido (se dio de baja)'),
    ]

    envio = models.ForeignKey(EnvioMasivo, on_delete=models.CASCADE, related_name='destinatarios')
    email = models.EmailField()
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    error = models.CharField(max_length=300, blank=True)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('envio', 'email')]
        ordering = ['id']

    def __str__(self):
        return f'{self.email} · {self.estado}'
