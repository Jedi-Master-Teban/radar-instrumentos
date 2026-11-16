import json

import httpx
import pytest

from radar.collectors.base import LectorBloqueado
from radar.collectors.http import ClienteHttp
from radar.ingesta import FuentePrecios, cargar_listings
from radar.models import PrecioTienda


def test_cargar_listings_de_ebay(tmp_path):
    (tmp_path / "listings.json").write_text(json.dumps({"ebay": [
        ["147682231982", "Gibson Les Paul Studio 2019", "COP $3 316 700.00", "o Mejor oferta|+COP $165 835.00 por el envío", "De segunda mano", "https://i/x.webp"],
        ["147682231983", "Gibson Les Paul Studio en Japón", "$900.00", "or Best Offer|de Japón", "Pre-Owned", ""],
        ["147682231984", "Gibson <b>SG</b> & Co", "$1,000.00", "Buy It Now|Free delivery", "Pre-Owned", ""]]}))
    ls = cargar_listings(tmp_path, trm=3316.70)
    assert [l.id_externo for l in ls] == ["147682231982", "147682231984"]
    assert ls[0].precio_usd == 1000.0 and ls[0].envio_us_usd == 50.0 and ls[0].acepta_ofertas
    assert ls[1].titulo == "Gibson <b>SG</b> & Co" and not ls[1].acepta_ofertas


def test_sin_archivo_no_hay_listings(tmp_path):
    assert cargar_listings(tmp_path, 3300) == []


def test_fuente_precios_filtra_por_palabras_y_condicion(tmp_path):
    (tmp_path / "p.json").write_text(json.dumps([
        {"fuente": "reverb", "titulo": "Gibson Les Paul Studio 2020 Ebony", "precio": 1100, "condicion": "usado"},
        {"fuente": "reverb", "titulo": "Gibson Les Paul Studio", "precio": 1699, "condicion": "nuevo"},
        {"fuente": "reverb", "titulo": "Gibson Les Paul Standard", "precio": 2200, "condicion": "usado"},
        {"fuente": "x", "titulo": "sin precio"}]))
    f = FuentePrecios(tmp_path / "p.json", [PrecioTienda("ebay", "GIBSON LES-PAUL STUDIO faded", 950, "usado")])
    assert sorted(i.precio for i in f("Gibson Les Paul Studio", "usado")) == [950, 1100]
    assert [i.precio for i in f("Gibson Les Paul Studio", "nuevo")] == [1699]
    assert f("Fender Jazzmaster", "usado") == []


def test_cliente_http():
    def handler(req):
        if "bloqueo" in req.url.host:
            return httpx.Response(403)
        if "roto" in req.url.path:
            return httpx.Response(200, text="<html>")
        return httpx.Response(200, json={"ok": 1})
    c = ClienteHttp(httpx.Client(transport=httpx.MockTransport(handler)), pausa=0)
    assert c.json("https://tienda.co", "/x.json") == {"ok": 1}
    assert c.json("https://tienda.co", "/roto") is None
    with pytest.raises(LectorBloqueado):
        c.json("https://bloqueo.co", "/x.json")
