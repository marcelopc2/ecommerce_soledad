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

    def __str__(self):
        return self.name

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL de la imagen (hasta que configuremos AWS S3)")
    is_main = models.BooleanField(default=False, help_text="¿Es la imagen principal?")

    def __str__(self):
        return f"Image for {self.product.name}"
