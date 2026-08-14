"""Pasa lo que hay hoy al sistema de categorías, SIN cambiarle nada a nadie.

El día que esto corre, todo alumno existente tiene que seguir viendo exactamente
los mismos modelos disponibles y con las mismas fechas de desbloqueo. Para eso
se crea una categoría "General" que replica la configuración global de hoy
(AjustesAula.cursos_iniciales, goteo semanal) y se le cuelga todo lo que existe:

  - los cursos activos, conservando su orden actual
  - los productos que hoy otorgan cursos
  - las membresías, ancladas a su propia fecha de creación (que es exactamente
    lo que usaba el cálculo anterior)
  - los diplomas

La migración es reversible: al revertirla se borra la categoría y sus vínculos,
y el sistema vuelve a leer `Product.courses` / `Membership.courses`, que no se
tocan en ningún momento.
"""
from django.db import migrations


NOMBRE = 'General'
SLUG = 'general'


def crear_categoria_general(apps, schema_editor):
    CourseCategory = apps.get_model('lms', 'CourseCategory')
    CategoryCourse = apps.get_model('lms', 'CategoryCourse')
    Course = apps.get_model('lms', 'Course')
    Membership = apps.get_model('lms', 'Membership')
    MembershipCategory = apps.get_model('lms', 'MembershipCategory')
    Diploma = apps.get_model('lms', 'Diploma')
    AjustesAula = apps.get_model('lms', 'AjustesAula')
    Product = apps.get_model('catalog', 'Product')

    cursos = list(Course.objects.filter(is_active=True).order_by('order', 'id'))
    hay_algo = cursos or Membership.objects.exists() or Product.objects.exists()
    if not hay_algo:
        # Base recién creada (tests, instalación nueva): no hay nada que migrar
        # y crear una categoría vacía solo ensucia.
        return

    # El mismo número que hoy usa el goteo para TODOS los alumnos. Si nunca se
    # tocó la pantalla de ajustes, la fila no existe y el default del modelo (3)
    # es justo lo que estaba rigiendo.
    ajustes = AjustesAula.objects.first()
    iniciales = ajustes.cursos_iniciales if ajustes else 3

    categoria, _ = CourseCategory.objects.get_or_create(
        slug=SLUG,
        defaults={'nombre': NOMBRE, 'modo': 'GOTEO', 'cursos_iniciales': iniciales},
    )

    # El orden dentro de la categoría arranca replicando el orden global, que es
    # el que el cálculo anterior usaba para la fila semanal.
    CategoryCourse.objects.bulk_create([
        CategoryCourse(categoria=categoria, curso=curso, orden=i + 1)
        for i, curso in enumerate(cursos)
    ], ignore_conflicts=True)

    # Solo los productos que hoy otorgan cursos: si un producto no daba acceso a
    # nada, sumarle la categoría le regalaría contenido que nunca vendió.
    for producto in Product.objects.all():
        if producto.courses.exists():
            producto.categories.add(categoria)

    # Ancla = created_at de la membresía, que es EXACTAMENTE lo que usaba
    # get_course_access antes. Así las fechas de desbloqueo no se mueven ni un día.
    MembershipCategory.objects.bulk_create([
        MembershipCategory(membership=m, categoria=categoria, obtenida_en=m.created_at)
        for m in Membership.objects.all()
    ], ignore_conflicts=True)

    Diploma.objects.filter(categoria__isnull=True).update(categoria=categoria)


def deshacer(apps, schema_editor):
    CourseCategory = apps.get_model('lms', 'CourseCategory')
    # Borrar la categoría se lleva en cascada sus vínculos (CategoryCourse,
    # MembershipCategory) y deja los diplomas sin categoría, que es el estado
    # previo. `Product.courses` y `Membership.courses` nunca se tocaron.
    CourseCategory.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0009_categorias_de_cursos'),
        ('catalog', '0017_categorias_de_cursos'),
    ]

    operations = [
        migrations.RunPython(crear_categoria_general, deshacer),
    ]
