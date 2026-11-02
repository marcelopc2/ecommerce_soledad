"""Lo que se escribe en el checkout y en el formulario de contacto.

Las validaciones del navegador se saltan con un POST directo: lo que decide es
el servidor. Nombres reales (tildes, ñ, O'Higgins, guiones) tienen que pasar;
marcas de código, no.
"""
from django.test import SimpleTestCase

from catalog.serializers import ContactSerializer
from payments.serializers import CheckoutSerializer


def checkout(**cambios):
    datos = {'product_ids': [1], 'email': 'mama@correo.cl', 'customer_name': 'Ana Pérez',
             'student_name': 'Beni', 'phone': '+56912345678'}
    datos.update(cambios)
    return CheckoutSerializer(data=datos)


ENVIO = {'region': 'Metropolitana', 'commune': 'Ñuñoa', 'address_street': 'Av. Irarrázaval',
         'address_number': '1234', 'address_detail': 'Depto 45-B', 'courier': 'Starken'}


class NombresTests(SimpleTestCase):
    def test_nombres_reales_pasan(self):
        for nombre in ("María José O'Higgins", 'Jean-Pierre Núñez', 'Sofía', 'Dr. Juan Pérez', 'Ñandú Ávila'):
            with self.subTest(nombre=nombre):
                self.assertTrue(checkout(customer_name=nombre, student_name=nombre).is_valid())

    def test_marcas_de_codigo_no_pasan(self):
        for malo in ('<script>alert(1)</script>', 'Ana"><img src=x>', '{{7*7}}', 'Ana; DROP TABLE',
                     '=HYPERLINK("x")', 'Ana\\nB', 'Ana`id`', 'Ana\x00'):
            with self.subTest(malo=malo):
                s = checkout(student_name=malo)
                self.assertFalse(s.is_valid())
                self.assertIn('student_name', s.errors)


class EnvioTests(SimpleTestCase):
    def test_direccion_normal_pasa(self):
        s = checkout(shipping=ENVIO)
        self.assertTrue(s.is_valid(), s.errors)

    def test_direccion_con_codigo_no_pasa(self):
        for campo in ('address_street', 'address_detail', 'commune'):
            with self.subTest(campo=campo):
                s = checkout(shipping={**ENVIO, campo: 'Calle <b>falsa</b>'})
                self.assertFalse(s.is_valid())


class ListaDeProductosTests(SimpleTestCase):
    def test_tiene_tope(self):
        self.assertFalse(checkout(product_ids=list(range(1, 500))).is_valid())


class ContactoTests(SimpleTestCase):
    def test_mensaje_normal_pasa(self):
        s = ContactSerializer(data={'nombre': 'Ana', 'apellido': 'Pérez', 'email': 'a@b.cl',
                                    'telefono': '+56 9 1111 2222', 'comentarios': '¿Despachan a Arica? <3'})
        self.assertTrue(s.is_valid(), s.errors)

    def test_nombre_con_codigo_no_pasa(self):
        s = ContactSerializer(data={'nombre': '<script>x</script>', 'email': 'a@b.cl'})
        self.assertFalse(s.is_valid())
