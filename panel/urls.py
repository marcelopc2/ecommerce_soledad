from django.urls import path
from . import views

app_name = 'panel'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ingresar/', views.login_view, name='login'),
    path('salir/', views.logout_view, name='logout'),

    path('productos/', views.products, name='products'),
    path('productos/nuevo/', views.product_form, name='product_new'),
    path('productos/<int:pk>/editar/', views.product_form, name='product_edit'),
    path('productos/<int:pk>/eliminar/', views.product_delete, name='product_delete'),
    path('productos/portada/reordenar/', views.products_reorder, name='products_reorder'),
    path('productos/<int:pk>/portada/', views.product_toggle_landing, name='product_toggle_landing'),

    path('pedidos/', views.orders, name='orders'),
    path('pedidos/<int:pk>/detalle/', views.order_detail, name='order_detail'),
    path('pedidos/<int:pk>/emitir-boleta/', views.order_invoice_issue, name='order_invoice_issue'),
    path('pedidos/<int:pk>/despachar/', views.order_shipment_dispatch, name='order_shipment_dispatch'),

    path('cursos/', views.courses, name='courses'),
    path('cursos/reordenar/', views.courses_reorder, name='courses_reorder'),
    path('cursos/nuevo/', views.course_form, name='course_new'),
    path('cursos/<int:pk>/editar/', views.course_form, name='course_edit'),
    path('cursos/<int:pk>/eliminar/', views.course_delete, name='course_delete'),
    path('cursos/<int:pk>/duplicar/', views.course_duplicate, name='course_duplicate'),
    path('cursos/<int:pk>/recursos/reordenar/', views.lessons_reorder, name='lessons_reorder'),
    path('recursos/<int:pk>/eliminar/', views.lesson_delete, name='lesson_delete'),
    path('recursos/<int:pk>/vista-previa/', views.lesson_preview, name='lesson_preview'),
    path('recursos/<int:pk>/vista-previa/imagen/', views.lesson_preview_image, name='lesson_preview_image'),
    path('recursos/<int:pk>/vista-previa/pdf/', views.lesson_preview_pdf, name='lesson_preview_pdf'),

    path('diplomas/nuevo/', views.diploma_form, name='diploma_new'),
    path('diplomas/<int:pk>/editar/', views.diploma_form, name='diploma_edit'),
    path('diplomas/<int:pk>/eliminar/', views.diploma_delete, name='diploma_delete'),
    path('diplomas/<int:pk>/vista-previa/', views.diploma_preview, name='diploma_preview'),

    path('membresias/', views.memberships, name='memberships'),
    path('membresias/<int:pk>/detalle/', views.membership_detail, name='membership_detail'),
    path('membresias/<int:pk>/nombres/', views.membership_names_update, name='membership_names_update'),
    path('membresias/<int:pk>/pausar/', views.membership_toggle_pause, name='membership_toggle_pause'),
    path('membresias/<int:pk>/usuario/', views.membership_toggle_user, name='membership_toggle_user'),
    path('membresias/<int:pk>/eliminar/', views.membership_delete, name='membership_delete'),
    path('membresias/<int:pk>/enviar-clave/', views.membership_send_reset, name='membership_send_reset'),
    path('membresias/<int:pk>/asignar-clave/', views.membership_set_password, name='membership_set_password'),

    path('facturas/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),

    # Contenido del sitio público: una entrada de menú por sección, en vez de
    # seis pestañas dentro de un cajón llamado "Configuración". Todas apuntan a
    # la misma vista; el `tab` decide qué se edita (ver SECCIONES_CONTENIDO).
    path('portada/como-funciona/', views.configuracion, {'tab': 'pasos'}, name='cfg_pasos'),
    path('portada/videos/', views.configuracion, {'tab': 'videos'}, name='cfg_videos'),
    path('portada/testimonios/', views.configuracion, {'tab': 'testimonios'}, name='cfg_testimonios'),
    path('portada/preguntas-frecuentes/', views.configuracion, {'tab': 'faqs'}, name='cfg_faqs'),
    path('portada/concurso/', views.configuracion, {'tab': 'concurso'}, name='cfg_concurso'),
    # El ritmo de entrega es del Aula, no de la portada: vive bajo Academia.
    path('academia/ritmo-de-entrega/', views.configuracion, {'tab': 'aula'}, name='cfg_aula'),

    # La antigua "Configuración" ya no existe como pantalla. Se deja la ruta
    # redirigiendo para que no muera un enlace guardado en favoritos.
    path('configuracion/', views.configuracion_legacy, name='config'),

    # Cuentas de gestión (solo superusuario)
    path('cuentas/', views.staff_users, name='staff_users'),
    path('cuentas/<int:pk>/activar/', views.staff_user_toggle, name='staff_user_toggle'),
    path('cuentas/<int:pk>/clave/', views.staff_user_password, name='staff_user_password'),
    path('cuentas/<int:pk>/eliminar/', views.staff_user_delete, name='staff_user_delete'),

    path('preguntas-frecuentes/nueva/', views.faq_form, name='faq_new'),
    path('preguntas-frecuentes/<int:pk>/editar/', views.faq_form, name='faq_edit'),
    path('preguntas-frecuentes/<int:pk>/estado/', views.faq_toggle_active, name='faq_toggle_active'),
    path('preguntas-frecuentes/<int:pk>/eliminar/', views.faq_delete, name='faq_delete'),
    path('preguntas-frecuentes/restaurar/', views.faq_restore_defaults, name='faq_restore_defaults'),

    path('concurso/ganadores/nuevo/', views.ganador_form, name='ganador_new'),
    path('concurso/ganadores/<int:pk>/editar/', views.ganador_form, name='ganador_edit'),
    path('concurso/ganadores/<int:pk>/eliminar/', views.ganador_delete, name='ganador_delete'),
    path('testimonios/nuevo/', views.testimonial_form, name='testimonial_new'),
    path('testimonios/<int:pk>/editar/', views.testimonial_form, name='testimonial_edit'),
    path('testimonios/<int:pk>/estado/', views.testimonial_toggle_active, name='testimonial_toggle_active'),
    path('testimonios/<int:pk>/eliminar/', views.testimonial_delete, name='testimonial_delete'),
    path('testimonios/restaurar/', views.testimonial_restore_defaults, name='testimonial_restore_defaults'),

    path('videos/nuevo/', views.video_form, name='video_new'),
    path('videos/<int:pk>/editar/', views.video_form, name='video_edit'),
    path('videos/<int:pk>/estado/', views.video_toggle_active, name='video_toggle_active'),
    path('videos/<int:pk>/eliminar/', views.video_delete, name='video_delete'),
    path('videos/restaurar/', views.video_restore_defaults, name='video_restore_defaults'),

    path('pasos/nuevo/', views.step_form, name='step_new'),
    path('pasos/<int:pk>/editar/', views.step_form, name='step_edit'),
    path('pasos/<int:pk>/estado/', views.step_toggle_active, name='step_toggle_active'),
    path('pasos/<int:pk>/eliminar/', views.step_delete, name='step_delete'),
    path('pasos/restaurar/', views.step_restore_defaults, name='step_restore_defaults'),
]
