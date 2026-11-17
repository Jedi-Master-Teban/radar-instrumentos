import json
from datetime import date

from radar import db
from radar.capturas import importar
from radar.captura_reverb import armar, conocidos

HOY = date(2026, 11, 17)


def repo(tmp_path):
    (tmp_path / "capturas").mkdir(parents=True)
    (tmp_path / "busquedas.json").write_text(json.dumps({"busquedas": [
        {"slug": "strandberg", "consulta": "strandberg", "categoria": "guitarra", "precio_max": 3500, "paginas": 2},
        {"slug": "stingray", "consulta": "music man stingray bass", "categoria": "bajo", "precio_max": 3500}]}))
    return tmp_path


def fila(i, titulo, precio, foto=""):
    return [str(i), titulo, precio, "excellent", 1, "2026-11-01", 0, foto]


def test_armar_escribe_una_captura_por_busqueda_y_omite_lo_no_asignado(tmp_path):
    d = repo(tmp_path)
    filas = [{"slug": "strandberg", "estado": "ok", "filas": [fila(1, "Strandberg Boden Prog NX 6", 1250, "s--x--/q/1.jpg"),
                                                                fila(2, "Strandberg gig bag", 90)]},
             {"slug": "stingray", "estado": "ok", "filas": [fila(3, "Music Man StingRay Special 4", 1900)]},
             {"slug": "desconocida", "estado": "ok", "filas": [fila(4, "x", 1)]}]
    r = armar(filas, {"1": ["Strandberg", "Boden Prog NX 6"], "3": ["Ernie Ball Music Man", "StingRay Special 4"]}, d, HOY)
    assert r == [{"slug": "strandberg", "estado": "ok", "guardadas": 1, "omitidas": 1},
                 {"slug": "stingray", "estado": "ok", "guardadas": 1, "omitidas": 0}]
    c = json.loads((d / "capturas" / "reverb-strandberg.json").read_text())
    p = c["publicaciones"][0]
    assert c["capturado"] == "2026-11-17" and p["foto"] == "https://rvb-img.reverb.com/i/s--x--/q/1.jpg" and p["url"] == "https://reverb.com/item/1"
    assert json.loads((d / "capturas" / "reverb-stingray.json").read_text())["publicaciones"][0]["categoria"] == "bajo"
    assert conocidos(d) == {"Ernie Ball Music Man": ["StingRay Special 4"], "Strandberg": ["Boden Prog NX 6"]}


def test_busqueda_fallida_conserva_la_captura_anterior(tmp_path):
    d = repo(tmp_path)
    armar([{"slug": "strandberg", "estado": "ok", "filas": [fila(1, "a", 1000)]}], {"1": ["Strandberg", "Boden"]}, d, HOY)
    r = armar([{"slug": "strandberg", "estado": "HTTP 403", "filas": []}], {}, d, HOY)
    assert r[0]["estado"] == "HTTP 403" and len(json.loads((d / "capturas" / "reverb-strandberg.json").read_text())["publicaciones"]) == 1


def test_publicacion_repetida_en_dos_capturas_cuenta_una_vez(con, tmp_path):
    carpeta = tmp_path / "capturas"
    carpeta.mkdir()
    def pub(i, precio):
        return {"id": str(i), "titulo": f"Strandberg Boden Prog NX 6 #{i}", "url": f"https://reverb.com/item/{i}",
                "precio_usd": precio, "marca": "Strandberg", "modelo": "Boden Prog NX 6", "estado": "excellent"}
    vieja = [pub(i, p) for i, p in enumerate([1250, 1650, 1700])]
    nueva = [pub(0, 1200), pub(1, 1650), pub(2, 1700), pub(3, 1750)]
    (carpeta / "2026-11-16-reverb-strandberg.json").write_text(json.dumps({"fuente": "reverb", "capturado": "2026-11-16", "publicaciones": vieja}))
    (carpeta / "reverb-strandberg.json").write_text(json.dumps({"fuente": "reverb", "capturado": "2026-11-17", "publicaciones": nueva}))
    importar(con, carpeta, 3316.7, HOY)
    assert con.execute("select count(*) from listings").fetchone()[0] == 4
    v = json.loads(con.execute("select datos from referencias_us").fetchone()[0])
    assert v["n"] == 4  # sin duplicar comparables
    d = json.loads(con.execute("select o.datos from oportunidades o join listings l on l.id=o.listing_id where l.id_externo='0'").fetchone()[0])
    assert d["listing"]["precio_usd"] == 1200  # manda la captura más reciente


def test_comando_captura_responde(capsys):
    from radar.__main__ import main
    assert main(["radar", "captura"]) == 1 and "armar" in capsys.readouterr().out


def test_captura_vieja_no_se_muestra_y_precios_usados_cuentan(con, tmp_path):
    carpeta = tmp_path / "capturas"
    carpeta.mkdir()
    pub = {"id": "e1", "fuente": "ebay", "titulo": "Gibson Les Paul Studio", "url": "https://www.ebay.com/itm/e1", "precio_usd": 900,
           "marca": "Gibson", "modelo": "Les Paul Studio", "estado": "bueno"}
    usados = [{"marca": "Gibson", "modelo": "Les Paul Studio", "precio_usd": p} for p in (1300, 1350, 1400)]
    (carpeta / "vieja.json").write_text(json.dumps({"fuente": "reverb", "capturado": "2026-10-01", "publicaciones": [pub]}))
    (carpeta / "nueva.json").write_text(json.dumps({"fuente": "reverb", "capturado": "2026-11-16", "publicaciones": [pub | {"id": "e2"}],
                                                    "precios_usados": usados}))
    importar(con, carpeta, 3316.7, HOY)
    filas = con.execute("select plataforma, id_externo from listings").fetchall()
    assert [tuple(f) for f in filas] == [("ebay", "e2")]  # la de octubre ya no aparece; la fuente por publicación manda
    d = json.loads(con.execute("select datos from oportunidades").fetchone()[0])
    assert d["valoracion_us"]["n"] == 4 and d["listing"]["plataforma"] == "ebay"
