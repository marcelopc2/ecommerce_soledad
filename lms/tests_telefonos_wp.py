"""Normalización de los teléfonos que vienen del volcado de WordPress.

El campo del panel acepta cualquier cosa a propósito, pero lo que se IMPORTA sí
conviene dejarlo parejo: en WordPress el mismo número aparece como
'+56993250900', '56993250900' y '993250900' según por dónde entró. Si se guardan
los tres tal cual, buscar a una familia por teléfono no encuentra nada.

Lo que no se reconoce como chileno se guarda tal cual: un número extranjero es
mejor feo que perdido.
"""
from django.test import SimpleTestCase

from lms.management.commands.telefonos_desde_wordpress import normalizar


class NormalizarTests(SimpleTestCase):
    def test_las_tres_formas_del_mismo_numero_quedan_iguales(self):
        """Es el caso que motiva todo: el mismo celular escrito de tres maneras."""
        esperado = ('+56993250900', True)
        self.assertEqual(normalizar('+56993250900'), esperado)
        self.assertEqual(normalizar('56993250900'), esperado)
        self.assertEqual(normalizar('993250900'), esperado)

    def test_ignora_espacios_y_guiones(self):
        self.assertEqual(normalizar('+56 9 9325 0900'), ('+56993250900', True))
        self.assertEqual(normalizar('9-9325-0900'), ('+56993250900', True))

    def test_un_fijo_chileno_tambien_se_reconoce(self):
        """Los fijos parten entre 2 y 8; el 2 es Santiago."""
        self.assertEqual(normalizar('223456789'), ('+56223456789', True))

    def test_la_basura_no_se_hace_pasar_por_chilena(self):
        """'123456789' tiene nueve dígitos pero ningún número chileno empieza
        en 1: convertirlo a +56123456789 sería inventar un teléfono."""
        numero, es_chileno = normalizar('123456789')
        self.assertFalse(es_chileno)
        self.assertEqual(numero, '123456789')

    def test_un_extranjero_se_guarda_tal_cual(self):
        numero, es_chileno = normalizar('04140184240')
        self.assertFalse(es_chileno)
        self.assertEqual(numero, '04140184240')

    def test_una_anotacion_sin_digitos_no_estorba(self):
        """'(casa)' no aporta dígitos, así que el número de abajo se reconoce
        igual y se guarda limpio. La anotación se pierde, y está bien: lo que se
        quiere de una importación es el número."""
        self.assertEqual(normalizar('  22 345 6789  (casa)  '), ('+56223456789', True))

    def test_una_anotacion_CON_digitos_deja_el_texto_intacto(self):
        """'anexo 12' mete dígitos de más, así que ya no parece un número
        chileno y se guarda tal cual. Es lo que se quiere: inventar un teléfono
        a partir de un texto ambiguo es peor que dejarlo feo."""
        numero, es_chileno = normalizar('22 345 6789 anexo 12')
        self.assertFalse(es_chileno)
        self.assertEqual(numero, '22 345 6789 anexo 12')

    def test_vacio_es_vacio(self):
        self.assertEqual(normalizar(''), ('', False))
        self.assertEqual(normalizar('   '), ('', False))
        self.assertEqual(normalizar(None), ('', False))
