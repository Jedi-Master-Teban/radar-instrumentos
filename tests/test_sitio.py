import json
from datetime import date

from pytest import approx

from radar import db, vistas
from radar.notify import SinAvisos
from radar.pipeline import correr
from radar.sitio import construir
from tests.conftest import HOY, listing
from tests.fakes import ModeloFalso, co, us


def datos(tmp_path, refs=()):
    (tmp_path / "capturas").mkdir(parents=True)
    pubs = [{"id": str(i), "titulo": f"Strandberg Boden Prog NX 6 #{i}", "url": f"https://reverb.com/item/{i}",
             "precio_usd": pr, "marca": "Strandberg", "modelo": "Boden Prog NX 6", "estado": "excellent", "ofertas": True}
            for i, pr in enumerate([1250, 1650, 1700, 1750, 1800])]
    pubs.append({"id": "9", "titulo": "Strandberg Boden Neck-Thru 6", "url": "https://reverb.com/item/9",
                 "precio_usd": 1900, "marca": "Strandberg", "modelo": "Boden Neck-Thru 6", "estado": "excellent"})
    (tmp_path / "capturas" / "2026-11-16-reverb-strandberg.json").write_text(json.dumps({
        "fuente": "reverb", "consulta": "strandberg", "capturado": "2026-11-16", "publicaciones": pubs,
        "precios_nuevos": [{"marca": "Strandberg", "modelo": "Boden Prog NX 6", "precio_usd": 2599}]}))
    (tmp_path / "parametros.json").write_text(json.dumps({"_nota": "x", "margen_objetivo": 0.25, "clave_rara": 1}))
    (tmp_path / "referencias_co.json").write_text(json.dumps(list(refs)))
    return tmp_path


def test_construir_escribe_todas_las_paginas(tmp_path):
    salida = tmp_path / "_site"
    r = construir(salida, datos(tmp_path / "d"), HOY, trm=3316.7, colombia=False, repo="dueno/radar")
    nombres = {p.name for p in salida.iterdir()}
    assert {"index.html", "explorar.html", "estado.html", ".nojekyll", "robots.txt"} <= nombres
    assert r["evaluadas"] == 6 and len([n for n in nombres if n.startswith("o-")]) == 6 and r["paginas"] == 9
    hoy = (salida / "index.html").read_text()
    assert 'href="o-' in hoy and 'href="explorar.html"' in hoy and "noindex" in hoy and "dueno/radar" in hoy
    assert "Seguimiento" not in hoy  # las pantallas locales no se publican
    est = (salida / "estado.html").read_text()
    assert "2026-11-16-reverb-strandberg.json" in est and "datos/parametros.json" in est
    assert "Corrida completa" not in est


def test_referencia_propia_del_repo_manda(tmp_path):
    construir(tmp_path / "a", datos(tmp_path / "d1"), HOY, trm=3316.7, colombia=False)
    sin = (tmp_path / "a" / "explorar.html").read_text()
    construir(tmp_path / "b", datos(tmp_path / "d2", [{"marca": "Strandberg", "modelo": "Boden Prog NX 6",
                                                       "usado_cop": 9000000}]), HOY, trm=3316.7, colombia=False)
    con = (tmp_path / "b" / "explorar.html").read_text()
    assert "estimada" in sin and "$9.000.000" in con and 'data-clase="reventa"' in con


def test_detalle_estatico_sin_formularios_locales(tmp_path):
    construir(tmp_path / "s", datos(tmp_path / "d"), HOY, trm=3316.7, colombia=False, repo="dueno/radar")
    pags = [p.read_text() for p in (tmp_path / "s").glob("o-*.html")]
    assert all('action="/oportunidad' not in t for t in pags)
    con_cuenta = [t for t in pags if 'id="datos"' in t]
    assert con_cuenta and "edit/main/datos/referencias_co.json" in con_cuenta[0] and 'data-estado="descartada"' in con_cuenta[0]


def test_cuenta_del_navegador_coincide_con_la_del_radar(con):
    con.execute("update watchlist set activo=0")
    con.execute("update watchlist set activo=1 where consulta='Fender electric guitar'")
    av = SinAvisos()
    correr(con, {"ebay": lambda c: [listing(500)]}, {"r": us()}, {"m": co()}, ModeloFalso(), av, 3270, HOY)
    o = vistas.cargar_ops(con)[0]
    c = vistas.cuentas(o["desglose"])
    assert c["techo"] == approx(o["oferta"]["techo_usd"]) and c["retiro"] == approx(o["oferta"]["retiro_usd"])
    assert c["apertura"] == approx(o["oferta"]["apertura_usd"], abs=0.01)
    assert c["margen"] == approx(o["margen_en_retiro"]) and c["piso"] == approx(o["venta"]["piso_cop"])
    assert c["lista"] == approx(o["venta"]["lista_cop"]) and c["flete_max"] == approx(o["flete_maximo_cop"])


def test_vigilar_cuenta_y_deja_de_insistir():
    import pytest

    from radar.collectors.base import LectorBloqueado
    from radar.sitio import vigilar
    estado, llamadas = {}, []

    def caida(c):
        llamadas.append(c)
        raise TimeoutError("lenta")
    f = vigilar("Lenta", caida, estado)
    for _ in range(5):
        with pytest.raises((TimeoutError, LectorBloqueado)):
            f("x")
    assert len(llamadas) == 3 and estado["Lenta"]["errores"] == 3 and "lenta" in estado["Lenta"]["ultimo_error"]
    g = vigilar("Buena", lambda c: [1] if c == "a" else [], estado)
    g("a"), g("b")
    assert estado["Buena"] == {"con_resultados": 1, "sin_resultados": 1, "errores": 0, "ultimo_error": ""}


def test_estado_muestra_cada_tienda(tmp_path, monkeypatch):
    import radar.sitio as sitio
    from radar.collectors import tiendas

    def falsa(http, t, consulta):
        if t["nombre"] == "Ortizo":
            raise TimeoutError("sin respuesta")
        return []
    monkeypatch.setattr(tiendas, "buscar_tienda_co", falsa)
    sitio.construir(tmp_path / "s", datos(tmp_path / "d"), HOY, trm=3316.7, colombia=True)
    t = (tmp_path / "s" / "estado.html").read_text()
    assert "no respondió" in t and "sin respuesta" in t and "La Colonial" in t and "0 de 2" in t
