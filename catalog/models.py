import re

from django.core.validators import FileExtensionValidator
from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=0, help_text="Precio en pesos chilenos (CLP)")
    stock = models.IntegerField(default=0, help_text="Inventario disponible (0 si es ilimitado/digital y no requiere tracking de stock)")
    is_digital = models.BooleanField(default=False, help_text="¿Es un pack de modelos digital? (No requiere envío)")
    is_active = models.BooleanField(default=True)

    # --- Oferta ---
    is_on_sale = models.BooleanField(default=False, help_text="Mostrar el producto en oferta (ribbon rojo)")
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=0, null=True, blank=True,
        help_text="Precio de oferta en CLP (se cobra este si el producto está en oferta)",
    )

    # --- Próximamente ---
    is_coming_soon = models.BooleanField(
        default=False, help_text="Marcar como 'Próximamente': se muestra pero no se puede comprar aún",
    )

    # --- Compra solo para alumnos ---
    # Las cuentas del LMS SOLO se crean al pagar una compra (ver
    # lms.services.grant_access_for_order), así que exigir sesión iniciada
    # equivale a exigir que la persona ya haya comprado antes -normalmente el
    # kit inicial con las piezas físicas-. Se valida en el servidor, en
    # payments.orders.build_order_from_request: el candado del frontend solo
    # es para la UX y se salta con un POST directo.
    requires_login = models.BooleanField(
        default=False,
        help_text="Solo se puede comprar con la sesión iniciada (para packs de modelos "
                  "o planes que requieren haber comprado antes el kit con las piezas)",
    )

    # --- Presentación en la landing (sección Nuestros Kits) ---
    show_on_landing = models.BooleanField(
        default=False, help_text="Mostrar este producto en la sección de kits de la portada (máximo 4)",
    )
    landing_order = models.PositiveIntegerField(
        default=0, help_text="Orden en la portada. Los 3 primeros van en tarjetas; el 4º va en la tarjeta ancha de abajo",
    )
    landing_badge = models.CharField(
        max_length=40, blank=True, default='', help_text="Etiqueta de la tarjeta, ej: 'pago único' o 'pago mensual'",
    )
    price_note = models.CharField(
        max_length=40, blank=True, default='', help_text="Nota junto al precio, ej: '/ pago único'",
    )
    features = models.TextField(
        blank=True, default='', help_text="Beneficios de la tarjeta, uno por línea",
    )
    highlight = models.BooleanField(
        default=False, help_text="Destacar esta tarjeta con el estilo morado",
    )

    # --- LMS: qué acceso otorga comprar este producto ---
    courses = models.ManyToManyField(
        'lms.Course', related_name='products', blank=True,
        help_text="Cursos a los que da acceso la compra de este producto",
    )
    access_months = models.PositiveIntegerField(
        default=12, help_text="Meses de acceso al LMS incluidos al comprar este producto",
    )
    
    # Dimensiones para Shipit (Envíos)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, help_text="Peso en KG")
    width_cm = models.DecimalField(max_digits=5, decimal_places=2, default=30.00, help_text="Ancho en CM")
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, default=20.00, help_text="Alto en CM")
    length_cm = models.DecimalField(max_digits=5, decimal_places=2, default=30.00, help_text="Largo en CM")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def effective_price(self):
        """Precio que se cobra: el de oferta si está en oferta y definido, si no el normal."""
        if self.is_on_sale and self.sale_price is not None:
            return self.sale_price
        return self.price

    @property
    def features_list(self):
        """Beneficios como lista (una línea = un ítem)."""
        return [line.strip() for line in self.features.splitlines() if line.strip()]

    def __str__(self):
        return self.name

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL de la imagen (hasta que configuremos AWS S3)")
    is_main = models.BooleanField(default=False, help_text="¿Es la imagen principal?")

    def __str__(self):
        return f"Image for {self.product.name}"


# Set original de preguntas frecuentes (las que ya estaban fijas en la landing).
# Vive acá, no solo en la migración de datos, para que el botón "restaurar por
# defecto" del panel pueda recrearlas en cualquier momento sin tocar la BD a mano.
DEFAULT_FAQS = [
    {
        'question': '¿Qué es Ingenio Blocks?',
        'answer': 'Ingenio Blocks es una plataforma educativa que combina la entretención con el aprendizaje práctico. Con nuestro kit educativo STEM que contiene más de 400 piezas (bloques) + motor y batería y acceso a nuestra plataforma, los niños desde los 6 años pueden acceder a más de 100 modelos motorizados —uno nuevo cada semana— con instrucciones paso a paso.',
    },
    {
        'question': '¿Qué aprenden los niños con Ingenio Blocks?',
        'answer': 'A través de la construcción de modelos motorizados, los niños aprenden principios esenciales de matemáticas, física y mecánica, mientras cultivan su creatividad, pensamiento crítico y capacidad para resolver problemas.',
    },
    {
        'question': '¿Qué edad deben tener los participantes?',
        'answer': 'Nuestra plataforma está diseñada para niños y niñas desde los 6 años. El formato amigable les permite avanzar a su propio ritmo.',
    },
    {
        'question': '¿Cómo funcionan los programas?',
        'answer': 'Al adquirir tu kit, obtienes acceso a nuestra Aula Virtual, donde cada semana se libera un nuevo modelo motorizado con instrucciones paso a paso. Cada modelo plantea un nuevo desafío, aumentando gradualmente en dificultad.',
    },
    {
        'question': '¿Qué tipo de metodología de aprendizaje usa Ingenio Blocks?',
        'answer': 'Usamos metodologías de aprendizaje en espiral: cada proyecto está diseñado para explorar, crear, aprender y avanzar, fortaleciendo habilidades cognitivas, motoras y sociales.',
    },
    {
        'question': '¿Es necesario tener conocimientos previos en robótica o programación?',
        'answer': 'No, no se requiere ningún conocimiento previo. Las instrucciones paso a paso permiten que cualquier niño comience a construir desde el primer día.',
    },
]


class FAQManager(models.Manager):
    def restore_defaults(self):
        """Borra TODAS las preguntas actuales (incluidas las agregadas/editadas
        a mano) y recrea el set original de DEFAULT_FAQS. Acción destructiva a
        propósito: es el botón "restaurar por defecto" del panel."""
        self.all().delete()
        self.bulk_create([
            FAQ(question=f['question'], answer=f['answer'], order=i)
            for i, f in enumerate(DEFAULT_FAQS, start=1)
        ])


class FAQ(models.Model):
    """Pregunta frecuente de la landing (sección "Preguntas Frecuentes").
    Editable desde el panel; DEFAULT_FAQS es el set con el que arranca el
    sitio y al que se puede volver con FAQ.objects.restore_defaults()."""
    question = models.CharField(max_length=300)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0, help_text="Posición en la lista. Se asigna solo al crear.")
    is_active = models.BooleanField(default=True, help_text="Se muestra en la landing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FAQManager()

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Pregunta frecuente'
        verbose_name_plural = 'Preguntas frecuentes'

    def __str__(self):
        return self.question


# Set original de testimonios (antes eran 4 tarjetas idénticas hardcodeadas
# en la landing). Vive acá, no solo en la migración de datos, para que el
# botón "restaurar por defecto" del panel pueda recrearlos en cualquier
# momento sin tocar la BD a mano.
DEFAULT_TESTIMONIALS = [
    {
        'name': 'Mario Gomez',
        'location': 'Santiago, Chile',
        'quote': 'Queríamos una actividad educativa y con diversión garantizada. Con este plan mensual encontramos la mezcla ideal de teoría y armado práctico.',
        'rating': 5,
    },
    {
        'name': 'Francisca Rojas',
        'location': 'Viña del Mar, Chile',
        'quote': 'Mi hija espera el modelo de cada semana con muchas ganas. Ha aprendido a seguir instrucciones y a resolver problemas sola, algo que antes le costaba.',
        'rating': 5,
    },
    {
        'name': 'Diego Herrera',
        'location': 'Concepción, Chile',
        'quote': 'Excelente forma de alejar a los niños de las pantallas sin perder la parte entretenida. El armado en equipo se volvió un momento familiar.',
        'rating': 5,
    },
    {
        'name': 'Camila Soto',
        'location': 'Antofagasta, Chile',
        'quote': 'Los materiales son de buena calidad y las instrucciones son muy claras. Mi hijo de 8 años arma los modelos casi sin ayuda.',
        'rating': 5,
    },
]


class TestimonialManager(models.Manager):
    def restore_defaults(self):
        """Borra TODOS los testimonios actuales (incluidos los agregados/editados
        a mano) y recrea el set original de DEFAULT_TESTIMONIALS. Acción
        destructiva a propósito: es el botón "restaurar por defecto" del panel."""
        self.all().delete()
        self.bulk_create([
            Testimonial(
                name=t['name'], location=t['location'], quote=t['quote'],
                rating=t['rating'], order=i,
            )
            for i, t in enumerate(DEFAULT_TESTIMONIALS, start=1)
        ])


class Testimonial(models.Model):
    """Testimonio de la landing (sección "Testimonios"). Editable desde el
    panel; DEFAULT_TESTIMONIALS es el set con el que arranca el sitio y al
    que se puede volver con Testimonial.objects.restore_defaults()."""
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=120)
    quote = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5, help_text="Estrellas, de 1 a 5")
    order = models.PositiveIntegerField(default=0, help_text="Posición en la lista. Se asigna solo al crear.")
    is_active = models.BooleanField(default=True, help_text="Se muestra en la landing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TestimonialManager()

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Testimonio'
        verbose_name_plural = 'Testimonios'

    def __str__(self):
        return f'{self.name} ({self.location})'


# YouTube entrega el link en varios formatos según de dónde se copie (barra de
# direcciones, botón "Compartir", "Insertar", Shorts...). Se acepta cualquiera
# y se extrae el ID de 11 caracteres, así la clienta pega lo que tenga a mano.
YOUTUBE_ID_PATTERNS = [
    r'(?:youtube\.com/watch\?(?:.*&)?v=)([\w-]{11})',   # youtube.com/watch?v=ID
    r'(?:youtu\.be/)([\w-]{11})',                        # youtu.be/ID
    r'(?:youtube\.com/embed/)([\w-]{11})',               # youtube.com/embed/ID
    r'(?:youtube\.com/shorts/)([\w-]{11})',              # youtube.com/shorts/ID
    r'^([\w-]{11})$',                                    # solo el ID pelado
]


def extract_youtube_id(value):
    """Devuelve el ID de 11 caracteres del video, o '' si no se reconoce."""
    value = (value or '').strip()
    for patron in YOUTUBE_ID_PATTERNS:
        match = re.search(patron, value)
        if match:
            return match.group(1)
    return ''


class LandingVideoManager(models.Manager):
    def restore_defaults(self):
        """Vuelve a los 3 videos originales de la sección "Sobre el Mundo Ingenio
        Blocks". Ojo: NO recrea las portadas (son archivos subidos), solo los
        textos y links; hay que volver a subir las imágenes. Por eso el panel
        avisa de esto en el modal de confirmación."""
        self.all().delete()
        self.bulk_create([
            LandingVideo(
                title=v['title'], description=v['description'],
                youtube_url=v['youtube_url'], order=i,
            )
            for i, v in enumerate(DEFAULT_LANDING_VIDEOS, start=1)
        ])


class LandingVideo(models.Model):
    """Video de la sección "Sobre el Mundo Ingenio Blocks" de la portada.
    La clienta administra el link de YouTube, la portada y el texto desde
    /gestion/configuracion/ sin tocar código."""
    title = models.CharField(max_length=120, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    youtube_url = models.CharField(
        max_length=300,
        help_text="Pega el link de YouTube tal cual (youtube.com/watch?v=…, youtu.be/… o el ID)",
    )
    cover = models.FileField(
        upload_to='landing_videos/', blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text="Imagen de portada del video (JPG, PNG o WEBP). Ideal horizontal, 16:9.",
    )
    order = models.PositiveIntegerField(default=0, help_text="Posición en la lista. Se asigna solo al crear.")
    is_active = models.BooleanField(default=True, help_text="Se muestra en la landing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LandingVideoManager()

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Video de la portada'
        verbose_name_plural = 'Videos de la portada'

    @property
    def youtube_id(self):
        return extract_youtube_id(self.youtube_url)

    def __str__(self):
        return self.title


class LandingStepManager(models.Manager):
    def restore_defaults(self):
        """Vuelve a los 3 pasos originales de "Cómo funciona". Ojo: NO recrea
        las fotos (son archivos subidos), solo textos, color e ícono; hay que
        volver a subir las imágenes. El modal del panel lo avisa."""
        self.all().delete()
        self.bulk_create([
            LandingStep(
                title=p['title'], description=p['description'],
                color=p['color'], icon=p['icon'], order=i,
            )
            for i, p in enumerate(DEFAULT_LANDING_STEPS, start=1)
        ])


class LandingStep(models.Model):
    """Paso de la sección "Cómo funciona" de la portada. El número (01, 02, 03)
    NO se edita: sale del orden, así nunca queda una numeración saltada."""

    # El color pinta el marco de la foto y el círculo del ícono; se elige de la
    # paleta de la marca en vez de dejar un campo libre, para que no entre un
    # color que rompa el diseño.
    COLOR_CHOICES = [
        ('#6a3093', 'Morado'),
        ('#00a63e', 'Verde'),
        ('#ff6101', 'Naranjo'),
        ('#8200db', 'Morado brillante'),
        ('#ffcb00', 'Amarillo'),
    ]
    # Los íconos son SVG dibujados en el frontend (no imágenes), así que acá
    # solo se guarda cuál usar.
    ICON_CHOICES = [
        ('kit', 'Carrito de compras'),
        ('aula', 'Pantalla / Aula virtual'),
        ('juega', 'Mando de videojuego'),
    ]

    title = models.CharField(max_length=140, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    photo = models.FileField(
        upload_to='landing_steps/', blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text="Foto del paso (JPG, PNG o WEBP). Ideal horizontal.",
    )
    color = models.CharField(max_length=7, choices=COLOR_CHOICES, default='#6a3093')
    icon = models.CharField(max_length=10, choices=ICON_CHOICES, default='kit')
    order = models.PositiveIntegerField(default=0, help_text="Posición en la lista. Se asigna solo al crear.")
    is_active = models.BooleanField(default=True, help_text="Se muestra en la landing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LandingStepManager()

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Paso de "Cómo funciona"'
        verbose_name_plural = 'Pasos de "Cómo funciona"'

    def __str__(self):
        return self.title


DEFAULT_LANDING_STEPS = [
    {
        'title': 'Adquiere tu Kit Ingenio Blocks',
        'description': 'Recibe en casa tu set de bloques físicos de alta calidad y prepárate para abrir la puerta a un mundo de creatividad tangible para tu hijo.',
        'color': '#6a3093', 'icon': 'kit', 'photo_asset': 'paso1.png',
    },
    {
        'title': 'Ingresa a nuestra Aula Virtual',
        'description': 'Desbloquea tu acceso exclusivo a la plataforma interactiva. Encuentra cientos de guías visuales paso a paso, retos divertidos y proyectos nuevos que se actualizan constantemente.',
        'color': '#00a63e', 'icon': 'aula', 'photo_asset': 'paso2.png',
    },
    {
        'title': 'Juega y disfruta',
        'description': 'Observa cómo tu pequeño da vida a sus propias ideas. Aprende jugando de forma autónoma, fomenta su concentración y desarrolla habilidades clave mientras se divierte.',
        'color': '#ff6101', 'icon': 'juega', 'photo_asset': 'paso3.png',
    },
]


# Set original de la sección (los que estaban fijos en Landing.jsx). Los IDs de
# YouTube son PLACEHOLDER hasta que la clienta cargue los videos reales.
DEFAULT_LANDING_VIDEOS = [
    {
        'title': 'Taladro y Herramientas',
        'description': 'Aprende cómo un motor convierte la energía eléctrica en movimiento que permite hacer girar una broca de taladro.',
        'youtube_url': 'dQw4w9WgXcQ',
        'cover_asset': 'video-taladro.png',
    },
    {
        'title': 'Caleidoscopio',
        'description': '¡Explora el maravilloso mundo de la óptica y la creatividad, donde cada giro revela una nueva y deslumbrante combinación de colores y formas!',
        'youtube_url': 'dQw4w9WgXcQ',
        'cover_asset': 'video-caleidoscopio.png',
    },
    {
        'title': 'Centrífuga de Ropa',
        'description': 'Descubre cómo este ingenioso mecanismo transforma la tarea de lavar en un proceso rápido y eficiente.',
        'youtube_url': 'dQw4w9WgXcQ',
        'cover_asset': 'video-centrifuga.png',
    },
]
