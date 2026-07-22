from django import forms
from django.db.models import Max
from catalog.models import Product, FAQ, Testimonial, LandingVideo, LandingStep, extract_youtube_id
from lms.models import Course, Lesson, Membership, Diploma


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
        fields = [
            'name', 'slug', 'description', 'price',
            'is_digital', 'is_active', 'courses', 'access_months',
            'weight_kg', 'width_cm', 'height_cm', 'length_cm',
            # oferta / próximamente / compra restringida
            'is_on_sale', 'sale_price', 'is_coming_soon', 'requires_login',
            # portada
            'show_on_landing', 'landing_badge',
            'price_note', 'features', 'highlight',
        ]
        labels = {
            'name': 'Nombre',
            'slug': 'Dirección web (se genera sola desde el título)',
            'description': 'Descripción',
            'price': 'Precio (CLP)',
            'is_digital': 'Producto digital (no requiere envío)',
            'is_active': 'Visible en la tienda',
            'courses': 'Cursos que otorga esta compra',
            'access_months': 'Meses de acceso al Aula Virtual',
            'weight_kg': 'Peso (kg)',
            'width_cm': 'Ancho (cm)',
            'height_cm': 'Alto (cm)',
            'length_cm': 'Largo (cm)',
            'is_on_sale': 'En oferta (muestra una cinta roja en la portada)',
            'sale_price': 'Precio de oferta (CLP)',
            'is_coming_soon': 'Próximamente (no se puede comprar aún)',
            'requires_login': 'Solo para alumnos (exige iniciar sesión para comprarlo)',
            'show_on_landing': 'Mostrar en la portada (sección de kits)',
            'landing_badge': 'Etiqueta de la tarjeta',
            'price_note': 'Nota junto al precio',
            'features': 'Beneficios (uno por línea)',
            'highlight': 'Destacar tarjeta (estilo morado)',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'courses': forms.CheckboxSelectMultiple(),
            'features': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Acceso al aula virtual por 6 meses.\n24 modelos (1 cada semana).\nCertificado de aprobación.'}),
            'landing_badge': forms.TextInput(attrs={'placeholder': 'pago único'}),
            'price_note': forms.TextInput(attrs={'placeholder': '/ pago único'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['courses'].required = False
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
        """No hay límite duro para marcar 'portada': el que sobra del top 4 queda
        en cola (no se muestra) hasta que se arrastre a un puesto ≤ 4 desde la lista
        de productos. Al marcar por primera vez, se agrega al final de la cola;
        al desmarcar, se limpia su posición."""
        obj = super().save(commit=False)
        if obj.show_on_landing:
            if not obj.landing_order:
                last = Product.objects.filter(show_on_landing=True).exclude(pk=obj.pk).aggregate(
                    m=Max('landing_order'))['m'] or 0
                obj.landing_order = last + 1
        else:
            obj.landing_order = 0
        if commit:
            obj.save()
            self.save_m2m()
        return obj


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
    class Meta:
        model = Course
        fields = ['title', 'slug', 'description', 'image_url', 'is_active']
        labels = {
            'title': 'Título',
            'slug': 'Dirección web (se genera sola desde el título)',
            'description': 'Descripción',
            'image_url': 'Imagen de portada (URL)',
            'is_active': 'Curso activo',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

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
        return obj


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
        fields = ['title', 'description', 'image_url', 'is_active']
        labels = {
            'title': 'Título del diploma',
            'description': 'Mensaje del diploma',
            'image_url': 'Imagen/fondo (opcional)',
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
        fields = ['question', 'answer', 'is_active']
        labels = {
            'question': 'Pregunta',
            'answer': 'Respuesta',
            'is_active': 'Visible en la landing',
        }
        widgets = {
            'question': forms.TextInput(attrs={'placeholder': '¿Qué es Ingenio Blocks?'}),
            'answer': forms.Textarea(attrs={'rows': 5}),
        }

    def save(self, commit=True):
        """Una pregunta nueva se agrega al final de la lista."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.order:
            last = FAQ.objects.aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
        return obj


class TestimonialForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ['name', 'location', 'quote', 'rating', 'is_active']
        labels = {
            'name': 'Nombre',
            'location': 'Ciudad, país',
            'quote': 'Testimonio',
            'rating': 'Estrellas (1 a 5)',
            'is_active': 'Visible en la landing',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Mario Gomez'}),
            'location': forms.TextInput(attrs={'placeholder': 'Santiago, Chile'}),
            'quote': forms.Textarea(attrs={'rows': 4}),
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }

    def save(self, commit=True):
        """Un testimonio nuevo se agrega al final de la lista."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.order:
            last = Testimonial.objects.aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
        return obj


class LandingVideoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LandingVideo
        fields = ['title', 'description', 'youtube_url', 'cover', 'is_active']
        labels = {
            'title': 'Título del video',
            'description': 'Descripción',
            'youtube_url': 'Link de YouTube',
            'cover': 'Portada',
            'is_active': 'Visible en la landing',
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
        """Un video nuevo se agrega al final de la lista."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.order:
            last = LandingVideo.objects.aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
        return obj


class LandingStepForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LandingStep
        fields = ['title', 'description', 'photo', 'color', 'icon', 'is_active']
        labels = {
            'title': 'Título del paso',
            'description': 'Descripción',
            'photo': 'Foto',
            'color': 'Color del marco y del ícono',
            'icon': 'Ícono',
            'is_active': 'Visible en la landing',
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
        """Un paso nuevo se agrega al final (el número 01/02/03 sale del orden)."""
        obj = super().save(commit=False)
        if not obj.pk and not obj.order:
            last = LandingStep.objects.aggregate(m=Max('order'))['m'] or 0
            obj.order = last + 1
        if commit:
            obj.save()
        return obj
