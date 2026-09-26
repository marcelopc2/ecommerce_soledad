import re
from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.text import slugify
from catalog.models import (
    Product, FAQ, Testimonial, LandingVideo, LandingStep, extract_youtube_id,
    SeccionConcurso, GanadorConcurso,
)
from comunicaciones.models import EnvioMasivo
from payments.models import Coupon
from shipments.models import PuntoRetiro

User = get_user_model()
from lms.models import (
    AjustesAula, CategoryCourse, Course, CourseCategory, Lesson, Membership, Diploma,
    PerfilUsuario,
)


class BootstrapFormMixin:
    """Agrega las clases de Bootstrap a todos los widgets del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'form-select')
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault('class', 'form-control')
            else:
                widget.attrs.setdefault('class', 'form-control')


class LoginForm(forms.Form):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'tu@correo.cl',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '••••••••',
        }),
    )


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        # Sin 'slug', 'show_on_landing' ni 'is_active' a propósito:
        #  · el slug se arma solo desde el nombre (ver save()); nadie que
        #    administre la tienda necesita escribir una dirección web.
        #  · publicar y destacar son UNA sola decisión en esta tienda: los
        #    productos se venden desde la portada, así que "activo" y "sale en
        #    la portada" van siempre juntos. Se deciden con el ojo de la lista;
        #    acá abajo, en save(), is_active se mantiene igual a show_on_landing.
        #    Antes eran dos controles en dos pantallas para lo mismo.
        fields = [
            'name', 'description', 'price', 'exento_iva',
            'is_digital', 'categories', 'courses', 'access_months',
            'weight_kg', 'width_cm', 'height_cm', 'length_cm',
            # oferta / próximamente / compra restringida
            'is_on_sale', 'sale_price', 'is_coming_soon', 'requires_login',
            # cómo se ve la tarjeta en la portada
            'landing_badge', 'price_note', 'features', 'highlight',
        ]
        # Etiquetas CORTAS: la explicación va en el globo de ayuda (ⓘ) del
        # template, no dentro del nombre del campo.
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'price': 'Precio (CLP)',
            'exento_iva': 'Exento de IVA',
            'is_digital': 'Producto digital',
            'categories': 'Categorías que incluye',
            'courses': 'Modelos sueltos extra',
            'access_months': 'Meses de acceso',
            'weight_kg': 'Peso (kg)',
            'width_cm': 'Ancho (cm)',
            'height_cm': 'Alto (cm)',
            'length_cm': 'Largo (cm)',
            'is_on_sale': 'En oferta',
            'sale_price': 'Precio de oferta (CLP)',
            'is_coming_soon': 'Próximamente',
            'requires_login': 'Necesita membresía',
            'landing_badge': 'Etiqueta',
            'price_note': 'Nota del precio',
            'features': 'Beneficios',
            'highlight': 'Destacar',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'categories': forms.CheckboxSelectMultiple(),
            'courses': forms.CheckboxSelectMultiple(),
            'features': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Acceso al aula virtual por 6 meses.\n24 modelos (1 cada semana).\nCertificado de aprobación.'}),
            'landing_badge': forms.TextInput(attrs={'placeholder': 'pago único'}),
            'price_note': forms.TextInput(attrs={'placeholder': '/ pago único'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['courses'].required = False
        self.fields['categories'].required = False
        self.fields['categories'].queryset = CourseCategory.objects.filter(is_active=True)
        self.fields['categories'].label_from_instance = (
            lambda c: f'{c.nombre} ({c.cursos_en_categoria.count()} modelos)'
        )
        # Se muestran en el orden semanal real (el mismo que se arrastra en
        # /gestion/cursos/) para que sea claro cuáles modelos otorga este kit.
        self.fields['courses'].queryset = Course.objects.order_by('order', 'id')
        self.fields['courses'].label_from_instance = lambda c: f"{c.order}. {c.title}"

    def clean(self):
        data = super().clean()

        # El precio de oferta es obligatorio (y menor al normal) si está en oferta.
        if data.get('is_on_sale'):
            sale = data.get('sale_price')
            price = data.get('price')
            if sale is None:
                self.add_error('sale_price', 'Indica el precio de oferta o desmarca "En oferta".')
            elif price is not None and sale >= price:
                self.add_error('sale_price', 'El precio de oferta debe ser menor al precio normal.')

        return data

    def save(self, commit=True):
        """El slug se arma acá y no en el formulario: es un dato técnico que solo
        sirve para la dirección web y no aporta nada a quien administra la tienda.

        Solo se genera al CREAR. Al editar se deja como está aunque cambie el
        nombre: el slug es parte de la URL pública, y regenerarlo rompería los
        enlaces que ya estén compartidos o indexados."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.slug:
            obj.slug = self._slug_unico(obj.name)
        # Publicado == en la portada. Un producto recién creado nace apagado y se
        # publica prendiendo su ojo en la lista; editar uno no cambia su estado.
        obj.is_active = obj.show_on_landing
        if commit:
            obj.save()
            self.save_m2m()
        return obj

    @staticmethod
    def _slug_unico(nombre):
        base = slugify(nombre) or 'producto'
        slug, n = base, 2
        # El slug es unique=True: si ya existe se le agrega un número al final
        # en vez de reventar con un error de base de datos.
        while Product.objects.filter(slug=slug).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug


class MembershipForm(BootstrapFormMixin, forms.ModelForm):
    """Los datos de contacto del alumno, todos editables.

    El correo no es un dato más: en este proyecto el `username` ES el correo
    (ver lms.services.grant_access_for_order), así que cambiarlo cambia también
    con qué se inicia sesión. Por eso se guarda en los DOS campos: si solo se
    tocara `email`, la persona seguiría entrando con el correo viejo y el nuevo
    no le serviría, sin ningún error visible.
    """

    email = forms.EmailField(
        label='Correo de registro',
        help_text='Es con el que inicia sesión y a donde llegan los avisos. '
                  'Si lo cambias, avísale: el anterior deja de servir.',
        widget=forms.EmailInput(attrs={'placeholder': 'nombre@correo.cl'}),
    )

    class Meta:
        model = Membership
        fields = ['parent_name', 'student_name', 'phone']
        labels = {
            'parent_name': 'Nombre del apoderado',
            'student_name': 'Nombre del alumno',
            'phone': 'Teléfono',
        }
        widgets = {
            'parent_name': forms.TextInput(attrs={'placeholder': 'Nombre y apellido'}),
            'student_name': forms.TextInput(attrs={'placeholder': 'Nombre del niño o niña'}),
            'phone': forms.TextInput(attrs={'placeholder': '+56 9 1234 5678'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El correo no vive en Membership sino en el User, así que hay que
        # traerlo a mano: un ModelForm no lo sabe buscar solo.
        if self.instance and self.instance.pk:
            self.fields['email'].initial = self.instance.user.email or self.instance.user.username

    def clean_email(self):
        """Normaliza y comprueba que no sea el correo de otra cuenta.

        Sin esto, guardar el correo de un alumno existente reventaba con un
        IntegrityError (username es único) y la clienta veía un error 500 en vez
        de "ese correo ya lo usa otra persona".
        """
        email = (self.cleaned_data['email'] or '').lower().strip()
        usuario = self.instance.user if self.instance and self.instance.pk else None

        chocan = User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email))
        if usuario is not None:
            chocan = chocan.exclude(pk=usuario.pk)
        if chocan.exists():
            raise forms.ValidationError(
                'Ese correo ya lo usa otra cuenta. Si son la misma persona con '
                'dos cuentas, hay que unirlas a mano, no cambiar el correo.'
            )
        return email

    def clean_phone(self):
        """Se acepta como lo escriban; solo se colapsan los espacios de más.

        No se valida el formato chileno como en el checkout a propósito: acá
        quien escribe es la administradora corrigiendo un dato, y a veces el
        número que tiene es un fijo, uno extranjero o con una anotación al lado.
        Rechazárselo sería impedirle guardar el único contacto que tiene.
        """
        return ' '.join((self.cleaned_data.get('phone') or '').split())

    def save(self, commit=True):
        membership = super().save(commit=False)
        email = self.cleaned_data['email']
        usuario = membership.user
        # Los dos, siempre: `username` es con lo que entra y `email` a donde le
        # llegan los correos. Dejarlos distintos es la forma más fácil de que
        # alguien quede sin poder entrar sin que nadie se entere.
        usuario.username = email
        usuario.email = email
        if commit:
            usuario.save(update_fields=['username', 'email'])
            membership.save()
        return membership


class MembershipExpiryForm(BootstrapFormMixin, forms.Form):
    """Cambiar a mano hasta cuándo tiene acceso un alumno.

    Existe porque no todo pago entra por el sitio: transferencias, efectivo en
    un taller, un mes de regalo por un problema, o corregir una fecha que llegó
    mal en la migración. Sin esto, la clienta no tiene forma de arreglarlo salvo
    pedirle a la persona que compre de nuevo.

    Es un Form y no un ModelForm porque el campo del modelo guarda fecha Y hora,
    pero a quien administra solo le interesa el día: la hora la ponemos nosotros
    al final de esa jornada (ver la vista), así "vence el 10" significa que el
    10 todavía puede entrar.
    """

    hasta = forms.DateField(
        label='Tiene acceso hasta el',
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        help_text='Ese día incluido: el acceso se corta a la medianoche siguiente.',
    )
    # Solo se muestra al reactivar una cuenta vencida (ver la plantilla), que es
    # el único caso donde la decisión cambia algo.
    reanudar_goteo = forms.BooleanField(
        required=False,
        label='Retomar la entrega semanal donde quedó',
        help_text='Si no lo marcas, recibe de una vez todos los modelos cuya '
                  'fecha pasó mientras estuvo vencida.',
    )

    def clean_hasta(self):
        hasta = self.cleaned_data['hasta']
        # Un año hacia atrás alcanza para corregir un error de tipeo; más que
        # eso, con la cantidad de ceros que tiene una fecha, es casi seguro un
        # dedazo (2025 por 2026) que dejaría a la familia sin acceso de golpe.
        limite = timezone.localdate() - timedelta(days=365)
        if hasta < limite:
            raise forms.ValidationError(
                'Esa fecha es de hace más de un año. Si de verdad quieres cortarle '
                'el acceso, pon la fecha de hoy.'
            )
        return hasta


class CourseForm(BootstrapFormMixin, forms.ModelForm):
    # No es un campo del modelo: la relación vive en CategoryCourse, que además
    # guarda el orden del curso DENTRO de cada categoría. Acá solo se elige a
    # cuáles pertenece; el orden se arrastra en la pantalla de la categoría.
    categorias = forms.ModelMultipleChoiceField(
        queryset=CourseCategory.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Categorías a las que pertenece',
        help_text='Un curso puede estar en varias. Si no marcas ninguna, ningún '
                  'alumno podrá verlo.',
    )

    class Meta:
        model = Course
        fields = ['title', 'slug', 'description', 'image_file', 'image_url',
                  'trailer_url', 'mostrar_en_portada', 'cuenta_como_desafio',
                  'is_active']
        labels = {
            'title': 'Título',
            'slug': 'Dirección web (se genera sola desde el título)',
            'description': 'Descripción',
            'image_file': 'Imagen de portada',
            'image_url': '…o pegar una dirección de internet',
            'trailer_url': 'Trailer de YouTube (portada)',
            'mostrar_en_portada': 'Mostrar entre los modelos de la portada',
            'is_active': 'Curso activo',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'trailer_url': forms.TextInput(
                attrs={'placeholder': 'https://www.youtube.com/watch?v=...'}),
        }

    def clean_trailer_url(self):
        """El trailer es opcional -una tarjeta con solo la foto es válida-, pero
        si se pega un link tiene que ser reproducible: si no, la tarjeta de la
        portada queda con un botón de play que no lleva a ninguna parte.

        Se guarda normalizado a /embed/ porque es lo que necesita el <iframe>;
        pegar el link de la barra del navegador tal cual dejaba el reproductor
        en blanco sin ningún aviso."""
        url = (self.cleaned_data.get('trailer_url') or '').strip()
        if not url:
            return url
        video_id = extract_youtube_id(url)
        if not video_id:
            raise forms.ValidationError(
                'No reconocimos ese link de YouTube. Cópialo desde la barra del '
                'navegador mientras ves el video, o usa el botón Compartir.')
        return f'https://www.youtube.com/embed/{video_id}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['categorias'].initial = CourseCategory.objects.filter(
                cursos_en_categoria__curso=self.instance,
            )

    def save(self, commit=True):
        """El orden (posición en la secuencia semanal) se maneja arrastrando en la
        lista de cursos, no en este formulario: los cursos nuevos se agregan al
        final de la fila automáticamente."""
        obj = super().save(commit=False)
        if not obj.order:
            last = Course.objects.exclude(pk=obj.pk).aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
            self._guardar_categorias(obj)
        return obj

    def _guardar_categorias(self, curso):
        """Sincroniza a qué categorías pertenece.

        Al agregarlo a una categoría se pone al FINAL de esa fila: meterlo al
        medio correría el calendario de todos los alumnos que ya la tienen y les
        cambiaría las fechas de lo que viene. Para moverlo se arrastra en la
        pantalla de la categoría, que es donde se ve el efecto.
        """
        elegidas = set(self.cleaned_data.get('categorias', []))
        actuales = set(CourseCategory.objects.filter(cursos_en_categoria__curso=curso))

        CategoryCourse.objects.filter(
            curso=curso, categoria__in=(actuales - elegidas),
        ).delete()

        for categoria in (elegidas - actuales):
            ultimo = categoria.cursos_en_categoria.aggregate(m=Max('orden'))['m'] or 0
            CategoryCourse.objects.create(
                categoria=categoria, curso=curso, orden=ultimo + 1,
            )


class LessonForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['title', 'lesson_type', 'description', 'video_embed_url',
                  'video_file', 'pdf_file', 'image_file']
        labels = {
            'title': 'Título del paso',
            'lesson_type': 'Tipo de paso',
            'description': 'Descripción (acompaña al paso)',
            'video_embed_url': 'Link del video de YouTube',
            'video_file': 'O sube un archivo de video',
            'pdf_file': 'Archivo PDF',
            'image_file': 'Imagen',
        }
        help_texts = {
            'video_embed_url': 'Pega el link tal como aparece en la barra del '
                               'navegador de YouTube. Nosotros lo convertimos.',
        }
        widgets = {
            # ids explícitos en 'title', 'description' e 'image_file': la misma
            # página trae el formulario del CURSO (CourseForm, más arriba) y el
            # del PASO nuevo (este form), y comparten esos tres nombres de
            # campo. Sin esto, el HTML terminaba con dos elementos con el mismo
            # id -inválido-, y el autocompletado y el foco de <label for> se
            # vuelven impredecibles cuando eso pasa: justo el tipo de falla que
            # se ve como "el botón no hace nada" sin ningún error en la consola.
            'title': forms.TextInput(attrs={'id': 'id_lesson_title'}),
            'description': forms.Textarea(attrs={
                'id': 'id_lesson_description', 'rows': 3,
                'placeholder': 'Instrucciones o paso a paso que acompañan a este recurso…'}),
            'image_file': forms.ClearableFileInput(attrs={'id': 'id_lesson_image_file'}),
            'video_embed_url': forms.TextInput(
                attrs={'placeholder': 'https://www.youtube.com/watch?v=...'}),
        }

    def clean_video_embed_url(self):
        """Acepta cualquier formato de link de YouTube y lo normaliza a /embed/.

        Antes el campo exigía el formato /embed/ pero no lo validaba: si la
        clienta pegaba el link normal de la barra del navegador (que es lo que
        hace cualquiera), se guardaba tal cual y el iframe quedaba EN BLANCO
        para el alumno, sin ningún error visible en el panel. La clienta no
        tenía forma de enterarse salvo entrando como alumna.

        Es la misma normalización que ya se aplicaba a los videos de la portada.
        """
        url = (self.cleaned_data.get('video_embed_url') or '').strip()
        if not url:
            return url

        video_id = extract_youtube_id(url)
        if video_id:
            return f'https://www.youtube.com/embed/{video_id}'

        # Vimeo y otros proveedores se dejan pasar tal cual: solo sabemos
        # reconocer YouTube, y rechazar lo demás sería peor.
        if 'vimeo.com' in url or '/embed/' in url:
            return url

        raise forms.ValidationError(
            'No reconocimos ese link de YouTube. Copia la dirección desde la '
            'barra del navegador mientras ves el video (o usa el botón '
            'Compartir de YouTube).'
        )

    def clean_video_file(self):
        """Tope de 60 MB.

        No es una limitación de disco: el Aula descarga el archivo ENTERO antes
        de mostrarlo (es la única forma de mandar el token de sesión, ver
        LessonVideo en CourseView.jsx), así que un archivo grande se traduce en
        un minuto de pantalla en blanco para el alumno. Lo que pasa de acá va a
        YouTube como "no listado" y se pega en el campo del link.
        """
        archivo = self.cleaned_data.get('video_file')
        TOPE = 60 * 1024 * 1024
        if archivo and getattr(archivo, 'size', 0) > TOPE:
            raise forms.ValidationError(
                'El video no puede pesar más de 60 MB: el alumno tendría que '
                'esperar a que se descargue entero antes de verlo. Para un video '
                'más largo, súbelo a YouTube como "no listado" y pega el link en '
                'el campo de arriba.'
            )
        return archivo

    def clean(self):
        data = super().clean()
        lesson_type = data.get('lesson_type')
        new = not self.instance.pk
        # Un paso de video sirve con cualquiera de los dos: el link de YouTube o
        # un archivo propio. Antes exigía el link, así que al subir solo el
        # archivo el formulario se negaba a guardar.
        tiene_video = (
            data.get('video_embed_url') or data.get('video_file')
            or (not new and self.instance.video_file)
        )
        if lesson_type == 'VIDEO' and not tiene_video:
            self.add_error(
                'video_embed_url',
                'Los pasos de video necesitan el link de YouTube o un archivo subido.',
            )
        if lesson_type == 'PDF' and not data.get('pdf_file') and new:
            self.add_error('pdf_file', 'Los recursos PDF necesitan un archivo.')
        if lesson_type == 'IMAGE' and not data.get('image_file') and new:
            self.add_error('image_file', 'Los recursos de imagen necesitan un archivo.')
        return data


class DiplomaForm(BootstrapFormMixin, forms.ModelForm):
    """Datos de un diploma.

    Sin `description`, `image_file` ni `image_url` a propósito: el certificado
    dejó de ser un diseño armable desde acá y pasó a ser la imagen de la marca,
    con el nombre, la cantidad de desafíos y la fecha escritos encima. Esos tres
    campos ya no se imprimían en ninguna parte y el formulario prometía algo que
    no iba a pasar ("si lo dejas vacío se usa el diseño lúdico por defecto").

    Lo que sí faltaba era la CATEGORÍA, que estaba en el formulario pero la
    plantilla nunca la pintaba: todos los diplomas se guardaban sin ella. Y es
    el campo que decide las dos cosas que importan: cuándo se gana y cuántos
    desafíos dice el certificado.
    """

    class Meta:
        model = Diploma
        fields = ['categoria', 'title', 'is_active']
        labels = {
            'categoria': 'Se gana al completar',
            'title': 'Título del diploma',
            'is_active': 'Activo',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Ej: Diploma Nivel Básico'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # OPCIONAL, y la diferencia importa:
        #   · con categoría  -> se gana al terminar TODA la categoría
        #   · sin categoría  -> se gana al terminar los modelos que están ANTES
        #                       en la fila, y el certificado cuenta esos
        # El segundo es el que sirve para un diploma intermedio. Haberla puesto
        # obligatoria mataba justo ese caso.
        self.fields['categoria'].required = False
        self.fields['categoria'].empty_label = 'Por posición en la fila (los modelos anteriores)'
        self.fields['categoria'].queryset = CourseCategory.objects.filter(is_active=True).order_by('nombre')

    def save(self, commit=True):
        """El orden se maneja arrastrando en la secuencia de cursos; un diploma
        nuevo se agrega al final."""
        obj = super().save(commit=False)
        if not obj.order:
            last = max(
                Course.objects.aggregate(m=Max('order'))['m'] or 0,
                Diploma.objects.exclude(pk=obj.pk).aggregate(m=Max('order'))['m'] or 0,
            )
            obj.order = last + 1
        if commit:
            obj.save()
        return obj


class FAQForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = FAQ
        # Sin 'is_active': se prende o apaga con el ojo de la lista de
        # Preguntas frecuentes, mismo criterio que Productos y Testimonios.
        fields = ['question', 'answer']
        labels = {
            'question': 'Pregunta',
            'answer': 'Respuesta',
        }
        widgets = {
            'question': forms.TextInput(attrs={'placeholder': '¿Qué es Ingenio Blocks?'}),
            'answer': forms.Textarea(attrs={'rows': 5}),
        }

    def save(self, commit=True):
        """Una pregunta nueva se agrega al final de la lista y nace oculta: se
        publica prendiendo su ojo en la lista."""
        obj = super().save(commit=False)
        if not obj.pk:
            obj.is_active = False
            if not obj.order:
                last = FAQ.objects.aggregate(m=Max('order'))['m'] or 0
                obj.order = last + 1
        if commit:
            obj.save()
        return obj


class TestimonialForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Testimonial
        # Sin 'is_active' a propósito: se prende o apaga con el ojo de la lista
        # de Testimonios (mismo patrón que la portada en Productos), no acá.
        # Antes había un check adentro Y el estado se veía en la lista, dos
        # controles para lo mismo.
        fields = ['name', 'location', 'quote', 'rating']
        labels = {
            'name': 'Nombre',
            'location': 'Ciudad, país',
            'quote': 'Testimonio',
            'rating': 'Estrellas (1 a 5)',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Mario Gomez'}),
            'location': forms.TextInput(attrs={'placeholder': 'Santiago, Chile'}),
            'quote': forms.Textarea(attrs={'rows': 4}),
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }

    def save(self, commit=True):
        """Un testimonio nuevo se agrega al final de la lista y nace oculto: se
        publica prendiendo su ojo en la lista, igual que un producto nuevo."""
        obj = super().save(commit=False)
        if not obj.pk:
            obj.is_active = False
            if not obj.order:
                last = Testimonial.objects.aggregate(m=Max('order'))['m'] or 0
                obj.order = last + 1
        if commit:
            obj.save()
        return obj


class LandingVideoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LandingVideo
        # Sin 'is_active': se prende o apaga con el ojo de la lista de Videos,
        # mismo patrón que Productos, Testimonios y Preguntas frecuentes.
        fields = ['title', 'description', 'youtube_url', 'cover']
        labels = {
            'title': 'Título del video',
            'description': 'Descripción',
            'youtube_url': 'Link de YouTube',
            'cover': 'Portada',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Taladro y Herramientas'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'youtube_url': forms.TextInput(attrs={'placeholder': 'https://www.youtube.com/watch?v=...'}),
        }

    def clean_youtube_url(self):
        """Se valida acá y no en el modelo para avisar en el formulario apenas
        se guarda: si el link no tiene un ID reconocible, el video no se podría
        reproducir y la tarjeta quedaría muerta en la portada."""
        url = self.cleaned_data['youtube_url']
        if not extract_youtube_id(url):
            raise forms.ValidationError(
                'No se reconoce el video en ese link. Pega la dirección completa de '
                'YouTube (por ejemplo https://www.youtube.com/watch?v=XXXXXXXXXXX).'
            )
        return url

    def clean_cover(self):
        """Máx 4 MB: son portadas que carga cada visitante de la landing."""
        cover = self.cleaned_data.get('cover')
        if cover and getattr(cover, 'size', 0) > 4 * 1024 * 1024:
            raise forms.ValidationError('La imagen no puede pesar más de 4 MB.')
        return cover

    def save(self, commit=True):
        """Un video nuevo se agrega al final de la lista y nace oculto: se
        publica prendiendo su ojo en la lista."""
        obj = super().save(commit=False)
        if not obj.pk:
            obj.is_active = False
            if not obj.order:
                last = LandingVideo.objects.aggregate(m=Max('order'))['m'] or 0
                obj.order = last + 1
        if commit:
            obj.save()
        return obj


class LandingStepForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LandingStep
        # Sin 'is_active': se prende o apaga con el ojo de la lista de Cómo
        # funciona, mismo patrón que Productos, Testimonios y Preguntas frecuentes.
        fields = ['title', 'description', 'photo', 'color', 'icon']
        labels = {
            'title': 'Título del paso',
            'description': 'Descripción',
            'photo': 'Foto',
            'color': 'Color del marco y del ícono',
            'icon': 'Ícono',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Adquiere tu Kit Ingenio Blocks'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_photo(self):
        """Máx 4 MB: son fotos que carga cada visitante de la landing."""
        photo = self.cleaned_data.get('photo')
        if photo and getattr(photo, 'size', 0) > 4 * 1024 * 1024:
            raise forms.ValidationError('La imagen no puede pesar más de 4 MB.')
        return photo

    def save(self, commit=True):
        """Un paso nuevo se agrega al final (el número 01/02/03 sale del orden)
        y nace oculto: se publica prendiendo su ojo en la lista."""
        obj = super().save(commit=False)
        if not obj.pk:
            obj.is_active = False
            if not obj.order:
                last = LandingStep.objects.aggregate(m=Max('order'))['m'] or 0
                obj.order = last + 1
        if commit:
            obj.save()
        return obj


class StaffUserForm(BootstrapFormMixin, forms.Form):
    """Alta de una cuenta de gestión.

    Es un Form y no un ModelForm porque la cuenta se identifica por correo: el
    login del panel llama a authenticate(username=<correo>), así que `username`
    y `email` tienen que guardar el mismo valor. Un ModelForm de User invitaría
    a llenar `username` con otra cosa y la cuenta no podría entrar.
    """

    email = forms.EmailField(
        label='Correo',
        widget=forms.EmailInput(attrs={'placeholder': 'persona@ingenioblocks.com'}),
    )
    nombre = forms.CharField(
        label='Nombre', max_length=150, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Nombre y apellido'}),
        help_text='Opcional. Solo para reconocer la cuenta en esta lista.',
    )
    password = forms.CharField(
        label='Contraseña', widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Mínimo 8 caracteres. Se la dictas a la persona; después no vuelve a verse.',
    )

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data['email'].lower().strip()
        # Se comprueban los dos campos porque las cuentas de alumno se crean con
        # username=email, pero cuentas antiguas podrían tener uno distinto.
        if User.objects.filter(username__iexact=email).exists() or \
                User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con ese correo.')
        return email

    def clean_password(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        pwd = self.cleaned_data['password']
        try:
            validate_password(pwd)
        except DjangoValidationError as e:
            raise forms.ValidationError(list(e.messages))
        return pwd


class AjustesAulaForm(BootstrapFormMixin, forms.ModelForm):
    """Ajustes del goteo del Aula Virtual (fila única)."""

    class Meta:
        model = AjustesAula
        fields = [
            'cursos_iniciales', 'bloqueados_visibles',
            'acceso_vencido', 'reanudar_goteo', 'diplomas_tras_vencer',
        ]
        labels = {
            'cursos_iniciales': 'Modelos disponibles al comprar',
            'bloqueados_visibles': 'Modelos bloqueados a la vista',
            'acceso_vencido': 'Qué ve cuando se le vence',
            'reanudar_goteo': 'Al renovar, el goteo sigue desde donde quedó',
            'diplomas_tras_vencer': 'Los diplomas ganados se siguen descargando',
        }

    def clean_cursos_iniciales(self):
        # 0 dejaría al recién llegado sin nada que abrir el día que pagó.
        n = self.cleaned_data['cursos_iniciales']
        if n < 1:
            raise forms.ValidationError('Tiene que ser al menos 1: si no, quien compra '
                                        'entra a un aula sin nada disponible.')
        return n


class SeccionConcursoForm(BootstrapFormMixin, forms.ModelForm):
    """Estado y textos de la franja del concurso (fila única)."""

    class Meta:
        model = SeccionConcurso
        fields = ['estado', 'etiqueta', 'titulo', 'intro', 'bases',
                  'boton_texto', 'boton_enlace', 'sello', 'imagen']
        widgets = {
            'bases': forms.Textarea(attrs={'rows': 6}),
            'intro': forms.TextInput(),
            'boton_enlace': forms.TextInput(attrs={
                'placeholder': 'mailto:contacto@ingenioblocks.com?subject=Concurso',
            }),
        }

    def clean_imagen(self):
        """Máx 4 MB: la carga cada visitante de la landing."""
        imagen = self.cleaned_data.get('imagen')
        if imagen and getattr(imagen, 'size', 0) > 4 * 1024 * 1024:
            raise forms.ValidationError('La imagen no puede pesar más de 4 MB.')
        return imagen

    def clean(self):
        """Avisa antes de publicar una sección a medio llenar. El estado
        "ganadores" necesita al menos un ganador visible; si no, la franja
        quedaría vacía en la portada."""
        datos = super().clean()
        if datos.get('estado') == SeccionConcurso.GANADORES:
            if not GanadorConcurso.objects.filter(is_active=True).exists():
                raise forms.ValidationError(
                    'Para mostrar los ganadores primero tienes que agregar al menos uno '
                    'visible, más abajo en esta misma pestaña.'
                )
        if datos.get('estado') == SeccionConcurso.CONVOCATORIA and not datos.get('titulo'):
            self.add_error('titulo', 'La convocatoria necesita un título.')
        return datos


class GanadorConcursoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = GanadorConcurso
        fields = ['nombre', 'edad', 'categoria', 'titulo', 'anio', 'texto', 'foto', 'tono', 'is_active']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Josefa Pérez'}),
            'edad': forms.TextInput(attrs={'placeholder': '7 años'}),
            'categoria': forms.TextInput(attrs={'placeholder': '6 a 8 años'}),
            'titulo': forms.TextInput(attrs={'placeholder': 'Ganadora'}),
            'anio': forms.TextInput(attrs={'placeholder': '2026'}),
            'texto': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto and getattr(foto, 'size', 0) > 4 * 1024 * 1024:
            raise forms.ValidationError('La foto no puede pesar más de 4 MB.')
        return foto

    def save(self, commit=True):
        """Un ganador nuevo se agrega al final de la lista."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.order:
            last = GanadorConcurso.objects.aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
        return obj


class CourseCategoryForm(BootstrapFormMixin, forms.ModelForm):
    """Una línea de contenido con su propio ritmo de entrega."""

    class Meta:
        model = CourseCategory
        fields = ['nombre', 'modo', 'cursos_iniciales', 'is_active']
        labels = {
            'nombre': 'Nombre de la categoría',
            'modo': 'Cómo se entregan los modelos',
            'cursos_iniciales': 'Modelos disponibles al comprar',
            'is_active': 'Categoría activa',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej: General, Premium, Institucional'}),
        }

    def save(self, commit=True):
        """El slug se genera solo: es un dato técnico que quien administra la
        tienda no tiene por qué inventar ni mantener único a mano."""
        obj = super().save(commit=False)
        if not obj.slug:
            base = slugify(obj.nombre) or 'categoria'
            slug, n = base, 2
            while CourseCategory.objects.exclude(pk=obj.pk).filter(slug=slug).exists():
                slug, n = f'{base}-{n}', n + 1
            obj.slug = slug
        if commit:
            obj.save()
        return obj


class MiCuentaForm(BootstrapFormMixin, forms.ModelForm):
    """La foto de perfil de la propia cuenta."""

    class Meta:
        model = PerfilUsuario
        fields = ['avatar']
        labels = {'avatar': 'Foto de perfil'}
        # FileInput y no el ClearableFileInput por omisión: aquel agrega su
        # propia casilla "Limpiar" junto a la ruta del archivo guardado, que
        # duplica al botón "Quitar la foto" y encima se lee peor.
        widgets = {'avatar': forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'})}


class CouponForm(BootstrapFormMixin, forms.ModelForm):
    """Alta y edición de un cupón de descuento.

    Las fechas usan <input type="datetime-local">, que es el único control de
    fecha+hora que el navegador muestra en el idioma del sistema. Django espera
    el formato ISO que ese input entrega, de ahí el input_formats explícito: sin
    él, toda fecha se rechazaba con "Escribe una fecha/hora válida".
    """

    class Meta:
        model = Coupon
        fields = [
            'code', 'description', 'discount_type', 'value',
            'min_purchase', 'starts_at', 'ends_at', 'max_uses', 'once_per_email',
        ]
        labels = {
            'code': 'Código',
            'description': 'Para qué es (nota interna)',
            'discount_type': 'Tipo de descuento',
            'value': 'Descuento',
            'min_purchase': 'Compra mínima',
            'starts_at': 'Empieza',
            'ends_at': 'Termina',
            'max_uses': 'Tope de usos',
            'once_per_email': 'Un uso por persona',
        }
        help_texts = {
            'code': 'Es lo que escribe el cliente al pagar. Sin espacios. Se guarda en mayúsculas.',
            'description': 'Solo para ti. El cliente no la ve.',
            'min_purchase': 'En pesos. Déjalo en 0 si sirve para cualquier compra.',
            'starts_at': 'Déjalo vacío para que sirva desde ya.',
            'ends_at': 'Déjalo vacío para que no venza. El cupón se apaga solo al llegar la fecha.',
            'max_uses': 'Cuántas compras pueden usarlo en total. Vacío = sin tope.',
            'once_per_email': 'El mismo correo no puede volver a usarlo.',
        }
        widgets = {
            'code': forms.TextInput(attrs={
                'placeholder': 'CYBER2026', 'autocapitalize': 'characters',
                'style': 'text-transform:uppercase',
            }),
            'description': forms.TextInput(attrs={'placeholder': 'CyberMonday 2026'}),
            'value': forms.NumberInput(attrs={'min': 1, 'placeholder': '25'}),
            'min_purchase': forms.NumberInput(attrs={'min': 0, 'step': 1000}),
            'max_uses': forms.NumberInput(attrs={'min': 1, 'placeholder': 'Sin tope'}),
            'starts_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M',
            ),
            'ends_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ('starts_at', 'ends_at'):
            self.fields[campo].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S']

    def clean_code(self):
        """El código viaja por mail, WhatsApp e Instagram y lo escribe gente a
        mano: se limita a letras, números y guiones para que no haya forma de
        que un espacio o una tilde lo deje inservible sin que se note."""
        code = (self.cleaned_data['code'] or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9\-]{3,30}', code):
            raise forms.ValidationError(
                'Usa entre 3 y 30 caracteres, solo letras, números y guiones. '
                'Sin espacios ni tildes: el cliente lo va a escribir a mano.'
            )
        return code

    def clean(self):
        datos = super().clean()
        tipo = datos.get('discount_type')
        valor = datos.get('value')
        inicio = datos.get('starts_at')
        fin = datos.get('ends_at')

        if tipo == Coupon.PORCENTAJE and valor is not None and valor > 100:
            self.add_error('value', 'Un porcentaje no puede pasar de 100.')
        if valor is not None and valor < 1:
            self.add_error('value', 'El descuento tiene que ser mayor que 0.')

        if inicio and fin and fin <= inicio:
            self.add_error('ends_at', 'La fecha de término tiene que ser posterior a la de inicio.')

        return datos


class PuntoRetiroForm(BootstrapFormMixin, forms.ModelForm):
    """La tienda donde la gente puede pasar a buscar su pedido."""

    class Meta:
        model = PuntoRetiro
        fields = [
            'activo', 'nombre', 'direccion', 'comuna', 'ciudad',
            'referencia', 'horario', 'instrucciones', 'mapa_url',
        ]
        labels = {
            'activo': 'Ofrecer retiro en tienda',
            'nombre': 'Nombre del lugar',
            'direccion': 'Dirección',
            'comuna': 'Comuna',
            'ciudad': 'Ciudad',
            'referencia': 'Cómo encontrarlo',
            'horario': 'Horario de retiro',
            'instrucciones': 'Qué tiene que hacer al llegar',
            'mapa_url': 'Link al mapa',
        }
        widgets = {
            'direccion': forms.TextInput(attrs={'placeholder': 'Av. Apoquindo 1234'}),
            'referencia': forms.TextInput(attrs={'placeholder': 'Piso 2, local 15, frente al ascensor'}),
            'horario': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Lunes a viernes de 10:00 a 18:00\nSábados de 10:00 a 14:00',
            }),
            'instrucciones': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Presenta tu número de pedido y tu carnet.',
            }),
            'mapa_url': forms.URLInput(attrs={'placeholder': 'https://maps.app.goo.gl/...'}),
        }

    def clean(self):
        """No se puede encender sin dirección ni horario.

        Sin dirección el retiro es una promesa sin lugar, y sin horario la gente
        llega cuando está cerrado. El checkout ya se protege solo (no ofrece la
        opción si falta alguno de los dos), pero avisarlo acá evita que la
        clienta lo marque, guarde, y se quede esperando una opción que nunca
        aparece sin entender por qué.
        """
        datos = super().clean()
        if datos.get('activo'):
            if not (datos.get('direccion') or '').strip():
                self.add_error('direccion', 'Para ofrecer retiro hay que decir dónde es.')
            if not (datos.get('horario') or '').strip():
                self.add_error('horario', 'Para ofrecer retiro hay que decir cuándo se puede ir.')
        return datos


class EnvioMasivoForm(BootstrapFormMixin, forms.ModelForm):
    """Redactar un correo masivo. Enviarlo es un paso aparte: ver el panel de
    Correos masivos y comunicaciones/envio.py."""

    class Meta:
        model = EnvioMasivo
        fields = ['asunto', 'cuerpo', 'boton_texto', 'boton_url', 'audiencia']
        labels = {
            'asunto': 'Asunto',
            'cuerpo': 'Texto del correo',
            'audiencia': 'A quién se le manda',
        }
        widgets = {
            'asunto': forms.TextInput(attrs={'placeholder': 'Ej: ¡Estrenamos página nueva!'}),
            'cuerpo': forms.Textarea(attrs={
                'rows': 10,
                'placeholder': 'Hola,\n\nTe contamos que...\n\nUn abrazo,\nEl equipo de Ingenio Blocks',
            }),
            'boton_texto': forms.TextInput(attrs={'placeholder': 'Conoce la nueva página'}),
            'boton_url': forms.URLInput(attrs={'placeholder': 'https://ingenioblocks.com'}),
            'audiencia': forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El mixin le pone `form-control` a todo lo que no reconoce, y a un
        # botón de radio eso lo deforma.
        self.fields['audiencia'].widget.attrs['class'] = 'form-check-input'

    def clean(self):
        datos = super().clean()
        # Un botón sin dirección no lleva a ningún lado, y una dirección sin
        # texto no se muestra: las dos a medias se descubrían recién en la prueba.
        if bool(datos.get('boton_texto')) != bool(datos.get('boton_url')):
            raise forms.ValidationError(
                'Para poner un botón necesitas las dos cosas: el texto y la dirección. '
                'Si no quieres botón, deja las dos en blanco.')
        return datos
