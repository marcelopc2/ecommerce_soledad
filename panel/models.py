"""Datos que solo existen para el panel de gestión: métricas de visitas y
registro de accesos.

Por qué acá y no en una app nueva: son tablas de apoyo del panel, no del
negocio. Ninguna otra app las lee.
"""
from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Métricas de visitas
#
# Se guardan AGREGADAS por día, no una fila por visita: un sitio con tráfico
# normal genera decenas de miles de vistas al mes, y guardarlas una por una
# haría crecer la base sin que nadie vaya a consultar el detalle. Lo que la
# clienta necesita es "cuánta gente entró en agosto", y eso se responde
# sumando contadores.
# ---------------------------------------------------------------------------

class VisitaDiaria(models.Model):
    """Páginas vistas por día y por ruta. Una fila por (día, ruta)."""
    fecha = models.DateField(db_index=True)
    ruta = models.CharField(max_length=200, help_text='Ej: / o /checkout')
    vistas = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('fecha', 'ruta')]
        ordering = ['-fecha']
        verbose_name = 'visita diaria'
        verbose_name_plural = 'visitas diarias'

    def __str__(self):
        return f'{self.fecha} {self.ruta}: {self.vistas}'


class VisitanteDiario(models.Model):
    """Un registro por visitante distinto y por día, para poder decir
    "hoy entraron 40 personas" y no solo "hubo 300 vistas".

    `huella` es un hash irreversible de IP + navegador + una sal secreta, y se
    recalcula cada día: NO se guarda la IP, no se puede volver atrás para saber
    quién era, y el mismo visitante en dos días distintos no queda ligado. Así
    se cuentan personas sin construir un perfil de nadie, que en un sitio para
    niños importa especialmente.
    """
    fecha = models.DateField(db_index=True)
    huella = models.CharField(max_length=64)

    class Meta:
        unique_together = [('fecha', 'huella')]
        ordering = ['-fecha']
        verbose_name = 'visitante diario'
        verbose_name_plural = 'visitantes diarios'


class OrigenDiario(models.Model):
    """De dónde llegan las visitas: buscador, Instagram, enlace directo..."""
    fecha = models.DateField(db_index=True)
    origen = models.CharField(max_length=120, help_text='Dominio de procedencia, o "directo"')
    visitas = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('fecha', 'origen')]
        ordering = ['-fecha']
        verbose_name = 'origen diario'
        verbose_name_plural = 'orígenes diarios'


# ---------------------------------------------------------------------------
# Registro de accesos
# ---------------------------------------------------------------------------

class RegistroAcceso(models.Model):
    """Quién entró (o intentó entrar), cuándo y desde dónde.

    Se guarda tanto el éxito como el fallo: una racha de fallos sobre la misma
    cuenta es la señal de que alguien está intentando entrar, y sin registrarla
    no hay forma de enterarse.

    `usuario` es SET_NULL y además se copia el correo en `email`: si la cuenta
    se borra, el registro tiene que sobrevivir -es justamente cuando más
    importa saber qué pasó- y con solo la relación quedaría una fila anónima.
    """
    ENTRADA = 'ENTRADA'
    FALLIDO = 'FALLIDO'
    SALIDA = 'SALIDA'
    TIPO_CHOICES = [
        (ENTRADA, 'Entró'),
        (FALLIDO, 'Intento fallido'),
        (SALIDA, 'Cerró sesión'),
    ]

    PANEL = 'PANEL'
    SITIO = 'SITIO'
    ZONA_CHOICES = [
        (PANEL, 'Panel de gestión'),
        (SITIO, 'Aula Virtual'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='accesos',
    )
    email = models.EmailField(
        blank=True, help_text='Copia del correo usado, sobrevive al borrado de la cuenta',
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, db_index=True)
    zona = models.CharField(max_length=10, choices=ZONA_CHOICES, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    dispositivo = models.CharField(
        max_length=200, blank=True, help_text='Navegador y sistema, resumido',
    )
    momento = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-momento']
        verbose_name = 'registro de acceso'
        verbose_name_plural = 'registros de acceso'
        indexes = [models.Index(fields=['zona', '-momento'])]

    def __str__(self):
        return f'{self.momento:%d-%m-%Y %H:%M} {self.email} {self.get_tipo_display()}'
