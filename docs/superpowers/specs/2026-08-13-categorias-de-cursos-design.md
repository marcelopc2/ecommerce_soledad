# Categorías de cursos — Diseño

**Proyecto:** IngenioBlocks · **Fecha:** 2026-08-13 · **Estado:** aprobado, pendiente de construir

## El problema

Hoy cada producto lleva una lista de cursos marcados a mano (`Product.courses`, M2M
directo). Eso trae dos costos:

1. **Cada curso nuevo hay que agregarlo producto por producto.** Si mañana se suma
   el modelo 9, hay que acordarse de marcarlo en Kit Inicial, y en cualquier otro
   producto que deba incluirlo. Nada lo hace solo, y olvidarlo pasa desapercibido.
2. **No hay forma de expresar "esta línea de cursos es premium".** Hoy "Kit 8
   modelos" apunta a los MISMOS 8 cursos que Kit Inicial (verificado en producción
   el 2026-08-13), así que comprarlo no desbloquea nada nuevo.

A futuro se suma un tercer caso: cuentas institucionales para colegios, con su
propio conjunto de cursos, donde algunos se comparten con el catálogo normal y
otros son exclusivos.

## Decisiones de producto (acordadas)

| Tema | Decisión |
|---|---|
| Un curso en varias categorías | **Sí.** Ej: un curso puede estar en "Normal" y en "Institucional" a la vez. |
| Categorías por producto | **Varias.** Un producto puede incluir más de una categoría. |
| Ritmo de entrega | **Por categoría**, no global. Cada una elige: todos los cursos abiertos de una, o goteo semanal con N abiertos al inicio. |
| Curso en dos categorías con reglas distintas | **Gana la más favorable.** Si Premium lo abre, está abierto, aunque en Normal todavía falten semanas. |
| Ancla del calendario | La fecha en que **ese alumno obtuvo esa categoría**, no la fecha de creación de la membresía. |
| Diplomas | **Pertenecen a una categoría.** Se ganan al completar los cursos de esa categoría. |
| Vista del alumno | **Una sola lista**, sin agrupar por categoría. Las categorías son maquinaria interna. |

## Modelo de datos

### `CourseCategory` (nuevo, app `lms`)

- `nombre`, `slug`, `is_active`
- `modo`: `GOTEO` | `TODO`
- `cursos_iniciales` (int): cuántos quedan abiertos el día que se obtiene la
  categoría. Solo aplica en modo `GOTEO`. Se muda acá el ajuste global
  `AjustesAula.cursos_iniciales`, que se elimina.

`AjustesAula` **no desaparece**: conserva `bloqueados_visibles` (cuántos cursos
bloqueados se muestran después de los disponibles), que es una decisión de
presentación de la lista final del alumno y sigue siendo global — la lista es una
sola, así que no tiene sentido por categoría.

### `CategoryCourse` (tabla intermedia curso ↔ categoría)

No basta un M2M pelado: **el orden del curso depende de la categoría desde la que
se lo mire**. Un curso puede ser el 5º de "Normal" y el 2º de "Institucional",
porque cada categoría contiene un subconjunto distinto. Por eso la tabla guarda:

- `categoria` (FK), `curso` (FK), `orden` (int, posición DENTRO de esa categoría)
- unique (`categoria`, `curso`)

`Course.order` (el orden global actual) deja de gobernar el desbloqueo y queda
solo como orden de presentación por defecto en el panel.

### `Product.categories` (M2M a `CourseCategory`)

Reemplaza a `Product.courses`.

### `MembershipCategory` (tabla intermedia membresía ↔ categoría)

La pieza nueva de verdad. Hoy la membresía solo recuerda **cuándo se creó**; con
categorías necesita recordar **cuándo obtuvo cada una**, porque cada categoría
corre su propio calendario.

- `membership` (FK), `categoria` (FK), `obtenida_en` (fecha)
- unique (`membership`, `categoria`)

Comprar un producto otorga sus categorías. Si el alumno ya tenía una categoría, la
fecha **no se pisa** (conserva la original: su calendario ya venía corriendo).

### `Diploma.categoria` (FK a `CourseCategory`)

Se gana al completar todos los cursos de esa categoría. Obligatorio (`null=False`):
un diploma sin categoría no tendría condición de entrega. La migración asigna
"General" a los diplomas existentes.

`Diploma.order` deja de compartir espacio con `Course.order` global. Cada diploma
se muestra **al final de los cursos de su categoría** en la lista del alumno; si
una categoría tuviera más de un diploma, `order` los desempata entre sí.

## Cálculo del desbloqueo

Los cursos del alumno pasan a **derivarse** de sus categorías en vez de ser una
lista fija copiada al comprar. Ese es el cambio que resuelve el problema original:
agregar un curso a "Normal" lo entrega a todos los que ya compraron Kit Inicial,
sin tocar el producto ni las membresías.

Por cada categoría de la membresía:

- **Modo `TODO`**: todos sus cursos abiertos desde `obtenida_en`.
- **Modo `GOTEO`**: fila ordenada por `CategoryCourse.orden`; los primeros
  `cursos_iniciales` abren el día `obtenida_en`; de ahí uno nuevo cada 7 días,
  **más la regla que ya existe hoy**: el siguiente no abre hasta completar el
  anterior (no se salta la fila).

El ancla sigue corriéndose por los días que la membresía estuvo pausada
(`total_paused_days`), igual que hoy.

**Un curso presente en varias categorías toma el estado más favorable.** Si
cualquiera de las categorías del alumno lo tiene abierto, está abierto. Si todas
lo tienen cerrado, se muestra el motivo de la que lo abrirá primero — la fecha más
cercana —, para no mostrar una fecha lejana cuando otra categoría lo va a liberar
antes.

El alumno ve **una sola lista**, ordenada por `Course.order` global, con unos
cursos abiertos y otros bloqueados. No se agrupa por categoría: es maquinaria
interna que él no necesita entender.

## Migración

El día del despliegue el comportamiento debe ser **idéntico al actual**. La
migración de datos:

1. Crea la categoría **"General"**: modo `GOTEO`, `cursos_iniciales` = el valor
   que hoy tiene `AjustesAula.cursos_iniciales`.
2. Le agrega todos los cursos activos, con `orden` = su `Course.order` actual.
3. Vincula todos los productos existentes a esa categoría.
4. A cada membresía existente le crea su `MembershipCategory` con
   `obtenida_en` = `membership.created_at`.
5. Asigna la categoría "General" a los diplomas existentes.

Resultado: mismas fechas de desbloqueo, mismo ritmo, cero sorpresas para quien ya
compró.

Verificado esto, se retiran `Product.courses` y `Membership.courses` para no
quedar con dos fuentes de verdad compitiendo. Es seguro porque los
administradores **nunca** asignan cursos a mano: `MembershipForm` solo edita
nombres (verificado en `panel/forms.py`), así que esos vínculos siempre salieron
de una compra.

Los cuatro puntos que hoy consultan `membership.courses` pasan a consultar los
cursos derivados de las categorías:

1. `lms/services.py::get_course_access` — arma la lista del alumno
2. `lms/services.py::_grant` — otorga al pagar (pasa a otorgar categorías)
3. `lms/views.py::CourseDetailView` — control de acceso al detalle de curso
4. `lms/views.py::_authorized_lesson_file` — control de acceso a PDFs e imágenes

## Cambios en el panel

- **Nueva sección "Categorías"**: crear, nombrar, elegir modo y cuántos iniciales,
  y arrastrar los cursos para ordenarlos dentro de esa categoría.
- **Curso**: casilleros de a qué categorías pertenece.
- **Producto**: "Modelos que incluye" (lista larga de cursos) pasa a ser
  "Categorías que incluye".
- **"Ritmo de entrega"** se queda, pero adelgaza: pierde "cuántos modelos
  disponibles al comprar" (se mudó a cada categoría) y conserva "cuántos
  bloqueados se muestran", que sigue siendo global.
- **Diploma**: selector de categoría.
- **Aviso**: marcar los cursos que quedaron **sin ninguna categoría**, porque en
  ese caso ningún alumno podría verlos nunca. Es un error silencioso fácil de
  cometer al crear un curso y olvidar etiquetarlo.

## Qué NO entra en este cambio

- Agrupar la vista del alumno por categoría (sigue siendo una lista única).
- Precios o reglas de cobro por categoría.
- Cuentas institucionales en sí (usuarios de colegio, cupos, panel del profesor).
  Este diseño deja el terreno preparado, pero esa funcionalidad es su propio
  proyecto.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Una membresía queda sin categorías y el alumno pierde acceso | La migración cubre todas las membresías existentes; los tests verifican que el acceso post-migración es idéntico al previo. |
| Un curso sin categoría se vuelve invisible | Aviso explícito en el panel. |
| El cálculo con varias categorías se vuelve lento (una consulta por categoría) | Precargar cursos y órdenes con `prefetch_related` y resolver en memoria, como ya hace `_completion_map`. |
| Cambiar el orden dentro de una categoría corre las fechas de alumnos en curso | Documentar el efecto en la pantalla de categorías: reordenar afecta a quienes todavía no llegan a ese punto. |

## Criterio de éxito

1. Agregar un curso a una categoría lo entrega automáticamente a todos los
   alumnos que ya tienen esa categoría, sin tocar productos ni membresías.
2. Un producto premium en modo `TODO` abre sus cursos apenas se compra, sin
   importar cuánto tiempo lleve la membresía.
3. Tras la migración, ningún alumno existente ve un cambio en sus fechas de
   desbloqueo.
