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
    assert "Corrida completa" not in est and "github.com/dueno/radar/actions/workflows/sitio.yml" in est
    assert 'href="estado.html#actualizar"' in hoy


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


def _una_op(con):
    con.execute("update watchlist set activo=0")
    con.execute("update watchlist set activo=1 where consulta='Fender electric guitar'")
    correr(con, {"ebay": lambda c: [listing(500)]}, {"r": us()}, {"m": co()}, ModeloFalso(), SinAvisos(), 3270, HOY)
    return vistas.cargar_ops(con)[0]


def test_cuenta_del_navegador_coincide_con_la_del_radar(con):
    o = _una_op(con)
    for k, e in o["escenarios"].items():
        c = vistas.cuentas(o["desglose"], comision=e["comision"])
        assert c["techo"] == approx(e["techo_usd"], abs=0.01) and c["compra"] == approx(e["compra_usd"], abs=0.01)
        assert c["apertura"] == approx(e["oferta"]["apertura_usd"], abs=0.01)
        assert c["neto_cop"] == approx(e["neto_cop"], abs=1) and c["neto_usd"] == approx(e["neto_usd"], abs=0.01)
        assert c["margen"] == approx(e["margen"]) and c["piso_cop"] == approx(e["piso_cop"], abs=1)
        assert c["flete_max_usd"] == approx(e["flete_maximo_usd"], abs=0.01)
        assert [l["cop"] for l in c["lineas"]] == approx([l["cop"] for l in e["lineas"]])
    c = vistas.cuentas(o["desglose"])
    assert c["lista_cop"] == approx(o["venta"]["lista_cop"]) and c["lista_usd"] == approx(c["lista_cop"] / 3270)


def test_cuenta_en_javascript_coincide_con_la_de_python(con, tmp_path):
    import shutil
    import subprocess
    if not shutil.which("node"):
        import pytest
        pytest.skip("sin node")
    o = _una_op(con)
    dg = o["desglose"]
    js = (vistas.PLANTILLAS / "_cuentas.js").read_text()
    casos = [(None, None, 0.05), (150, None, 0.10), (300, 6_000_000, 0.0)]
    prog = js + "\nvar dg=" + json.dumps(dg) + ";console.log(JSON.stringify([" + ",".join(
        f"cuentasRadar(dg,{'null' if f is None else f},{'null' if r is None else r},{c})" for f, r, c in casos) + "]));"
    (tmp_path / "c.js").write_text(prog)
    salida = json.loads(subprocess.run(["node", str(tmp_path / "c.js")], capture_output=True, text=True, check=True).stdout)
    for (f, r, c), j in zip(casos, salida):
        py = vistas.cuentas(dg, f, r, c)
        for k in ("techo", "compra", "apertura", "total_cop", "total_usd", "neto_cop", "neto_usd", "margen", "piso_cop",
                  "lista_cop", "flete_max_usd", "neto_apertura_cop", "neto_pedido_cop"):
            assert j[k] == approx(py[k], rel=1e-9, abs=1e-6), k
        assert [l["cop"] for l in j["lineas"]] == approx([l["cop"] for l in py["lineas"]])
        assert [l["usd"] for l in j["lineas_pedido"]] == approx([l["usd"] for l in py["lineas_pedido"]])


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


def test_fotos_con_respaldo_y_conteo_de_faltantes(tmp_path):
    d = datos(tmp_path / "d")
    ruta = d / "capturas" / "2026-11-16-reverb-strandberg.json"
    cap = json.loads(ruta.read_text())
    cap["publicaciones"][0]["foto"] = "https://rvb-img.reverb.com/i/x.jpg"
    ruta.write_text(json.dumps(cap))
    r = construir(tmp_path / "s", d, HOY, trm=3316.7, colombia=False)
    assert r["sin_foto"] == 5
    paginas = [(tmp_path / "s" / n).read_text() for n in ("index.html", "explorar.html")]
    paginas += [p.read_text() for p in (tmp_path / "s").glob("o-*.html")]
    con_foto = [t for t in paginas if "rvb-img.reverb.com/i/x.jpg" in t]
    assert con_foto
    for t in con_foto:  # si la imagen no carga, se quita y queda el nombre del modelo debajo
        assert 'onerror="this.remove()"' in t and '<span class="respaldo">Strandberg Boden Prog NX 6</span>' in t


def test_cache_de_colombia_entre_armados(con, tmp_path):
    from radar import sitio
    from radar.valuation import fijar_referencia_manual
    con.execute("insert into referencias_co(marca, modelo, usado_cop, nuevo_cop, n_usado, n_nuevo, fecha, manual, detalle)"
                " values('PRS','SE Custom 24',null,5400000,0,3,'2026-11-18',0,'[]')")
    fijar_referencia_manual(con, "Gibson", "Les Paul Studio", 6_000_000, HOY)
    ruta = tmp_path / "cache" / "referencias_co.json"
    assert sitio.guardar_cache(con, ruta) == 1  # las manuales vienen de referencias_co.json, no de la caché
    otra = db.conectar(":memory:")
    assert sitio.cargar_cache(otra, ruta) == 1
    f = otra.execute("select * from referencias_co where marca='PRS'").fetchone()
    assert f["nuevo_cop"] == 5_400_000 and f["fecha"] == "2026-11-18" and f["manual"] == 0
    assert sitio.cargar_cache(otra, tmp_path / "no-existe.json") == 0


def test_en_interes_en_el_sitio(tmp_path):
    from radar import interes
    d = datos(tmp_path / "d")
    (d / "busquedas.json").write_text(json.dumps({"busquedas": []}))
    cuerpo = "plataforma: reverb\nmarca: Strandberg\nmodelo: Boden Prog NX 6\ncategoria: guitarra\ntitulo: Strandberg Boden Prog NX 6 #0\nprecio_usd: 1250\nnota: Para sondear"
    interes.desde_issue(d, "En interés: reverb 0", cuerpo, HOY)
    cuerpo2 = cuerpo.replace("#0", "vendida").replace("1250", "1400")
    interes.desde_issue(d, "En interés: reverb 77", cuerpo2, HOY)
    cap = json.loads((d / "capturas" / interes.ARCHIVO).read_text())
    cap["publicaciones"][1]["anuncio"] = "sold"
    (d / "capturas" / interes.ARCHIVO).write_text(json.dumps(cap))
    salida = tmp_path / "_site"
    construir(salida, d, HOY, trm=3316.7, colombia=False, repo="dueno/radar")
    hoy = (salida / "index.html").read_text()
    seccion = hoy.split('id="t-interes"')[1].split("</section>")[0]
    assert "Para sondear" in seccion and "Vendida" in seccion and ">Activa<" in seccion
    assert 'class="esc dinero" data-c="5"' in seccion  # la activa trae su neto por comisión
    assert "ya no se evalúa" in seccion  # la vendida no
    assert "Quitar%20de%20inter%C3%A9s%3A%20reverb%2077" in seccion
    # en el estuche: la seguida ofrece quitar y las demás seguir, con el formulario ya lleno
    assert "issues/new?title=Quitar%20de%20inter%C3%A9s%3A%20reverb%200" in hoy
    assert "issues/new?title=En%20inter%C3%A9s%3A%20reverb%209&amp;body=" in hoy and "marca%3A%20Strandberg" in hoy
    det = next(p.read_text() for p in salida.glob("o-*.html") if "Para sondear" in p.read_text())
    assert 'id="t-seguida"' in det and "Activa · US$1.250" in det and 'chip interes">En interés' in det
