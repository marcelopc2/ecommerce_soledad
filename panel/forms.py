from django import forms
from django.db.models import Max
from django.utils.text import slugify
from catalog.models import (
    Product, FAQ, Testimonial, LandingVideo, LandingStep, extract_youtube_id,
    SeccionConcurso, GanadorConcurso,
)
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
            'name', 'description', 'price',
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
    class Meta:
        model = Membership
        fields = ['parent_name', 'student_name']
        labels = {
            'parent_name': 'Nombre del apoderado',
            'student_name': 'Nombre del alumno',
        }
        widgets = {
            'parent_name': forms.TextInput(attrs={'placeholder': 'Nombre y apellido'}),
            'student_name': forms.TextInput(attrs={'placeholder': 'Nombre del niño o niña'}),
        }


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
        fields = ['title', 'slug', 'description', 'image_file', 'image_url', 'is_active']
        labels = {
            'title': 'Título',
            'slug': 'Dirección web (se genera sola desde el título)',
            'description': 'Descripción',
            'image_file': 'Imagen de portada',
            'image_url': '…o pegar una dirección de internet',
            'is_active': 'Curso activo',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

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
        fields = ['title', 'lesson_type', 'description', 'video_embed_url', 'pdf_file', 'image_file']
        labels = {
            'title': 'Título del paso',
            'lesson_type': 'Tipo de paso',
            'description': 'Descripción (acompaña al paso)',
            'video_embed_url': 'Link del video de YouTube',
            'pdf_file': 'Archivo PDF',
            'image_file': 'Imagen',
        }
        help_texts = {
            'video_embed_url': 'Pega el link tal como aparece en la barra del '
                               'navegador de YouTube. Nosotros lo convertimos.',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Instrucciones o paso a paso que acompañan a este recurso…'}),
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

    def clean(self):
        data = super().clean()
        lesson_type = data.get('lesson_type')
        new = not self.instance.pk
        if lesson_type == 'VIDEO' and not data.get('video_embed_url'):
            self.add_error('video_embed_url', 'Los pasos de video necesitan el link.')
        if lesson_type == 'PDF' and not data.get('pdf_file') and new:
            self.add_error('pdf_file', 'Los recursos PDF necesitan un archivo.')
        if lesson_type == 'IMAGE' and not data.get('image_file') and new:
            self.add_error('image_file', 'Los recursos de imagen necesitan un archivo.')
        return data


class DiplomaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Diploma
        fields = ['categoria', 'title', 'description', 'image_file', 'image_url', 'is_active']
        labels = {
            'categoria': 'Se gana al completar',
            'title': 'Título del diploma',
            'description': 'Mensaje del diploma',
            'image_file': 'Imagen del diploma (opcional)',
            'image_url': '…o pegar una dirección de internet',
            'is_active': 'Activo',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Ej: Diploma Nivel Básico'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Mensaje que aparece en el diploma (opcional, hay uno por defecto).'}),
        }

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
