"""La bienvenida no entra a la vitrina de la portada.

No es un modelo armable: es la introducción al Aula. El alumno la recibe como
cualquier otro curso, pero la sección de la portada promete "nuestros modelos" y
ahí no pinta nada.

Esto se probó a mano en su momento y se volvió a romper en la primera
re-importación: el valor por omisión del campo es "sí mostrar", así que cada
volcado nuevo la devolvía a la portada. El error no da ningún síntoma salvo
entrar a mirar la galería, así que va cubierto.
"""
from django.test import SimpleTestCase

from lms.management.commands.importar_wordpress import Command


class BienvenidaFueraDeLaPortadaTests(SimpleTestCase):
    """Se prueba la REGLA, sin levantar el importador completo.

    El importador necesita un volcado de 187 MB y una carpeta de fotos; montar
    eso en un test sería más frágil que lo que se quiere proteger. Lo que puede
    romperse acá es el criterio de "¿esto es la bienvenida?", así que se prueba
    eso, escrito igual que en el importador.
    """

    def _va_a_la_portada(self, titulo):
        return not ('bienvenida' in titulo.lower())

    def test_la_bienvenida_queda_fuera(self):
        self.assertFalse(self._va_a_la_portada('Bienvenida a Ingenio Blocks'))

    def test_no_importa_como_este_escrita(self):
        """En el volcado el título viene con numeración y mayúsculas variables."""
        for titulo in ('BIENVENIDA', 'bienvenida', 'Bienvenida a Ingenio Blocks',
                       'Bienvenida 1'):
            with self.subTest(titulo=titulo):
                self.assertFalse(self._va_a_la_portada(titulo))

    def test_un_modelo_normal_si_entra(self):
        for titulo in ('Taladro y Herramientas', 'Excavadora sobre Oruga',
                       'Auto de Carrera', 'Carrusel'):
            with self.subTest(titulo=titulo):
                self.assertTrue(self._va_a_la_portada(titulo))

    def test_el_importador_usa_esta_misma_regla(self):
        """Si alguien cambia el criterio en el importador y no acá, este test
        deja de tener sentido en silencio. Se ata al código de verdad."""
        import inspect
        fuente = inspect.getsource(Command)
        self.assertIn("'bienvenida' in titulo.lower()", fuente)
        self.assertIn('mostrar_en_portada=not es_bienvenida', fuente)
