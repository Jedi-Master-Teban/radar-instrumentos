import json
from datetime import date

from radar import db
from radar.capturas import importar, leer_captura

HOY = date(2026, 11, 16)


def captura(tmp_path, nombre="2026-11-16-reverb-strandberg.json", barata=1250):
    pubs = [{"id": str(100 + i), "titulo": f"Strandberg Boden Prog NX 6 #{i}", "url": f"https://reverb.com/item/{100 + i}",
             "precio_usd": precio, "marca": "Strandberg", "modelo": "Boden Prog NX 6", "estado": "excellent",
             "ofertas": True, "publicada": "2026-11-01"}
            for i, precio in enumerate([barata, 1650, 1700, 1750, 1800])]
    pubs.append({"id": "900", "titulo": "Strandberg Boden Neck-Thru 6 Tremolo", "url": "https://reverb.com/item/900",
                 "precio_usd": 1900, "marca": "Strandberg", "modelo": "Boden Neck-Thru 6", "estado": "excellent"})
    pubs.append({"id": "901", "titulo": "rota", "precio_usd": "x"})
    (tmp_path / nombre).write_text(json.dumps({
        "fuente": "reverb", "categoria": "guitarra", "publicaciones": pubs,
        "precios_nuevos": [{"marca": "Strandberg", "modelo": "Boden Prog NX 6", "precio_usd": 2599}]}))
    return tmp_path


def test_leer_captura(tmp_path):
    pares, precios = leer_captura(captura(tmp_path) / "2026-11-16-reverb-strandberg.json")
    assert len(pares) == 6 and pares[0][1].estado == "excelente" and pares[0][0].acepta_ofertas
    assert sum(p.condicion == "nuevo" for p in precios) == 1


def test_importar_evalua_sin_modelo_y_guarda_observaciones(con, tmp_path):
    r = importar(con, captura(tmp_path, barata=1000), 3316.7, HOY)
    filas = {json.loads(f["datos"])["listing"]["id_externo"]: (f["tipo"], json.loads(f["datos"]))
             for f in con.execute("select tipo, datos from oportunidades")}
    assert r["archivos"] == 1 and len(filas) == 6
    assert filas["900"][1]["veredicto"] == "Sin comparables suficientes" and filas["900"][1]["prioritario"]
    tipo, d = filas["100"]
    assert tipo == "ganga" and d["veredicto"].startswith("Ganga") and d["valoracion_us"]["nuevo_usd"] == 2599
    assert filas["102"][0] == "observacion" and filas["102"][1]["veredicto"] == "A precio de mercado"
    assert con.execute("select count(*) from eventos where tipo='importacion'").fetchone()[0] == 1


def test_no_reimporta_si_no_cambio_y_si_cuando_cambia(con, tmp_path):
    importar(con, captura(tmp_path), 3316.7, HOY)
    assert importar(con, tmp_path, 3316.7, HOY) is None
    import os, time
    captura(tmp_path, barata=900)
    os.utime(tmp_path / "2026-11-16-reverb-strandberg.json", (time.time() + 5, time.time() + 5))
    assert importar(con, tmp_path, 3316.7, HOY) is not None
    d = json.loads(con.execute("select o.datos from oportunidades o join listings l on l.id=o.listing_id "
                               "where l.id_externo='100'").fetchone()[0])
    assert d["listing"]["precio_usd"] == 900 and "rebajado" in d["senales"]
    assert con.execute("select count(*) from oportunidades").fetchone()[0] == 6


def test_importar_no_alerta_ni_toca_listings_ajenos(con, tmp_path):
    from tests.conftest import listing
    lid, _ = db.guardar_listing(con, listing(500))
    con.execute("update listings set proceso='sin_valoracion_us' where id=?", (lid,))
    importar(con, captura(tmp_path, barata=1000), 3316.7, HOY)
    assert con.execute("select proceso from listings where id=?", (lid,)).fetchone()[0] == "sin_valoracion_us"
    assert con.execute("select count(*) from oportunidades where alertada=1").fetchone()[0] == 0


def test_carpeta_inexistente(con, tmp_path):
    assert importar(con, tmp_path / "nada", 3316.7, HOY) is None
