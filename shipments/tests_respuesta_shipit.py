"""Lo que Shipit devuelve al crear un envío, y cómo se lee.

Los nombres de los campos no se supusieron: salen de mirar la cuenta real de la
clienta con `GET /v/packages`, que tenía 5 envíos hechos desde el WordPress
viejo. Ahí se vio que **`label_url` no existe en Shipit**: la etiqueta viaja en
`ticket_shipit_pdf_url` y `ticket_url`. El código anterior la buscaba por un
nombre inventado, así que el envío quedaba guardado sin PDF que imprimir y nadie
se enteraba hasta que había que despachar.
"""
from django.test import SimpleTestCase

from shipments.services import _leer_respuesta_shipit


#: Un envío tal como lo devuelve la cuenta real, recortado a lo que se usa.
#: Los datos del cliente van inventados; los NOMBRES de los campos son los de
#: verdad, que es lo que importa acá.
RESPUESTA_REAL = {
    'id': 8951261,
    'reference': '#63636',
    'tracking_number': '713135319971',
    'ticket_shipit_pdf_url': 'https://shipit.cl/etiquetas/8951261.pdf',
    'ticket_url': 'https://chilexpress.cl/etiqueta/713135319971',
    'old_ticket_url_courier': 'https://viejo.courier.cl/x',
    'status': 'by_retired',
    'courier_for_client': 'chilexpress',
}


class LeerRespuestaTests(SimpleTestCase):
    def test_saca_los_tres_datos_de_una_respuesta_real(self):
        r = _leer_respuesta_shipit(RESPUESTA_REAL)
        self.assertEqual(r['reference'], '8951261')
        self.assertEqual(r['tracking_number'], '713135319971')
        self.assertEqual(r['label_url'], 'https://shipit.cl/etiquetas/8951261.pdf')

    def test_prefiere_el_pdf_de_shipit_sobre_la_del_courier(self):
        """Es el que la clienta imprime y pega en la caja; el del courier a
        veces pide iniciar sesión."""
        r = _leer_respuesta_shipit(RESPUESTA_REAL)
        self.assertIn('shipit.cl', r['label_url'])

    def test_si_falta_el_pdf_cae_a_la_etiqueta_del_courier(self):
        sin_pdf = {k: v for k, v in RESPUESTA_REAL.items() if k != 'ticket_shipit_pdf_url'}
        r = _leer_respuesta_shipit(sin_pdf)
        self.assertEqual(r['label_url'], 'https://chilexpress.cl/etiqueta/713135319971')

    def test_el_nombre_inventado_ya_no_manda_pero_se_acepta(self):
        """`label_url` se deja como último recurso por si Shipit lo agrega,
        pero nunca debe ganarle a los nombres que hoy existen de verdad."""
        con_ambos = dict(RESPUESTA_REAL, label_url='https://inventado/x.pdf')
        r = _leer_respuesta_shipit(con_ambos)
        self.assertIn('shipit.cl', r['label_url'])

    def test_una_respuesta_pelada_no_revienta(self):
        """Si Shipit cambia la forma, el envío tiene que guardarse igual: el
        pedido ya está pagado y perderlo por un campo es peor que no tener la
        etiqueta, que se puede bajar del panel de Shipit a mano."""
        r = _leer_respuesta_shipit({})
        self.assertEqual(r, {'reference': '', 'tracking_number': '', 'label_url': ''})

    def test_un_id_numerico_queda_como_texto(self):
        """`shipit_reference` es un CharField: guardar un int ahí lo convierte
        igual, pero compararlo después fallaba silenciosamente."""
        r = _leer_respuesta_shipit({'id': 123})
        self.assertEqual(r['reference'], '123')
        self.assertIsInstance(r['reference'], str)
