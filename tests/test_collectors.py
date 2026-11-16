import json

import pytest

from radar.collectors import ebay, facebook, mercadolibre, reverb, tiendas
from radar.collectors.base import LectorBloqueado, parece_bloqueo, parse_precio_usd
from tests.conftest import leer


@pytest.mark.parametrize("texto,esperado", [
    ("$1,249.99", 1249.99), ("US $450.00", 450.0), ("$520", 520.0),
    ("$450.00 to $600.00", None), ("Free", None), ("EUR 300,00", None), ("", None), ("450", None),
])
def test_parse_precio_usd(texto, esperado):
    assert parse_precio_usd(texto) == esperado


def test_parse_precio_cop_convierte_con_trm():
    assert parse_precio_usd("COP $2 752 835.43", trm=3300) == pytest.approx(834.19, abs=0.01)
    assert parse_precio_usd("COP $2 752 835.43") is None  # sin TRM no se adivina


def test_bloqueo_detectado():
    assert parece_bloqueo("<html><title>Pardon Our Interruption</title></html>")
    assert parece_bloqueo("<html></html>", "https://signin.ebay.com/x")
    assert not parece_bloqueo("<html><body>resultados</body></html>", "https://www.ebay.com/sch/")


# ---------- eBay ----------
def test_ebay_parse_activos():
    ls = {l.id_externo: l for l in ebay.parse_activos(leer("ebay_activos.html"), trm=3300)}
    # fuera: artículo en Japón, tarjeta de relleno "Shop on eBay" y precio en rango
    assert set(ls) == {"147682231982", "147682232067", "226001112223", "226001112225"}
    a = ls["147682231982"]
    assert a.url == "https://www.ebay.com/itm/147682231982" and a.acepta_ofertas
    assert a.precio_usd == pytest.approx(6_002_443.09 / 3300, abs=0.01)
    assert a.envio_us_usd == pytest.approx(49_810.05 / 3300, abs=0.01)
    assert a.titulo.startswith("Fender Player HSS") and a.fotos
    assert ls["147682232067"].hace_envios is False
    g = ls["226001112223"]
    assert g.precio_usd == 1049.99 and g.envio_us_usd == 0 and g.acepta_ofertas and g.estado_declarado == "Pre-Owned"
    s = ls["226001112225"]
    assert s.envio_us_usd == 48.5 and s.acepta_ofertas is False


def test_ebay_sin_trm_descarta_precios_en_cop():
    assert {l.id_externo for l in ebay.parse_activos(leer("ebay_activos.html"))} == {"226001112223", "226001112225"}


def test_ebay_html_sin_resultados():
    assert ebay.parse_activos("<html></html>") == []


# ---------- Reverb ----------
def test_reverb_parse_listings():
    ls = reverb.parse_listings(json.loads(leer("reverb_listings.json")))
    assert [l.id_externo for l in ls] == ["103861301", "103900002"]  # fuera: EUR, vendida, sin precio
    a, b = ls
    assert a.precio_usd == 730.0 and a.acepta_ofertas and a.estado_declarado == "excellent"
    assert a.url.startswith("https://reverb.com/item/103861301") and a.fecha_publicacion.isoformat() == "2026-11-07"
    assert "BARELY PLAYED" in a.descripcion and "<p>" not in a.descripcion
    assert a.envio_us_usd == 0 and b.envio_us_usd == 65.0


def test_reverb_respuesta_vacia():
    assert reverb.parse_listings(None) == [] and reverb.parse_listings({"listings": []}) == []


# ---------- Tiendas ----------
ORTIZO = {"nombre": "Ortizo", "origen": "https://ortizo.com.co", "plataforma": "shopify"}


def test_shopify():
    ps = tiendas.parse_shopify(json.loads(leer("shopify_suggest.json")), ORTIZO)
    assert [p.precio for p in ps] == [1072900.0, 1905900.0]  # fuera: agotada y sin precio
    assert ps[0].url == "https://ortizo.com.co/products/combo-guitarra-acustica-concert-fender-cc-60s-negra"
    assert ps[0].condicion == "nuevo" and ps[0].fuente == "Ortizo"


def test_woocommerce():
    ps = tiendas.parse_woocommerce(json.loads(leer("woo_products.json")), {"nombre": "MHS", "origen": "x"})
    assert [p.precio for p in ps] == [9330552.0, 9330552.0, 1500000.0]  # unidad menor aplicada; sin stock fuera


def test_guitar_center():
    usados = tiendas.parse_guitar_center(leer("guitarcenter.html"), "usado")
    nuevos = tiendas.parse_guitar_center(leer("guitarcenter.html"), "nuevo")
    assert [p.precio for p in usados] == [399.99, 674.99] and [p.precio for p in nuevos] == [799.99]
    assert tiendas.parse_guitar_center("<html></html>", "usado") == []


# ---------- Facebook (estructura supuesta) ----------
def test_facebook_us_solo_con_envio_y_sin_duplicados():
    ls = facebook.parse_busqueda(leer("fb_busqueda.html"))
    assert [(l.id_externo, l.precio_usd) for l in ls] == [("9001", 800.0)]
    assert ls[0].hace_envios and ls[0].url.endswith("/item/9001/")


def test_facebook_co():
    ps = facebook.parse_busqueda_co(leer("fb_busqueda_co.html"))
    assert [(p.precio, p.condicion) for p in ps] == [(3200000.0, "usado")]


def test_facebook_login_es_bloqueo():
    with pytest.raises(LectorBloqueado):
        facebook.parse_busqueda(leer("fb_login.html"))


# ---------- MercadoLibre (estructura supuesta) ----------
def test_mercadolibre():
    ps = mercadolibre.parse_busqueda(leer("meli_busqueda.html"))
    assert [(p.precio, p.condicion) for p in ps] == [(3200000.0, "usado"), (4899900.0, "nuevo")]
    assert ps[0].url == "https://articulo.mercadolibre.com.co/MCO-1-fender-player"


def test_ebay_busca_solo_articulos_ubicados_en_eeuu():
    u = ebay.url_busqueda("strandberg guitar", precio_min=400)
    assert "LH_LocatedIn=1" in u and "_stpos=33166" in u and "LH_PrefLoc" not in u and "_udlo=400" in u
