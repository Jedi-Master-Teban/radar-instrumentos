import json
from datetime import date

from radar import interes
from radar.capturas import leer_captura
from radar.captura_reverb import armar

HOY = date(2026, 11, 19)
FOTO = "https://rvb-img.reverb.com/i/s--x--/a.jpg"
CUERPO = """<!-- No cambies las líneas de abajo: el radar las lee -->
plataforma: reverb
id: 103081848
marca: PRS
modelo: SE Custom 24
categoria: guitarra
titulo: PRS SE Custom 24 2017 - 2019 - Whale Blue
precio_usd: 500
envio_usd: 0
estado: good
ofertas: 1
publicada: 2026-10-19
foto: https://rvb-img.reverb.com/i/s--x--/a.jpg
nota: Sondeo de mercado; sin promesa de compra
"""


def datos(tmp_path):
    d = tmp_path / "datos"
    (d / "capturas").mkdir(parents=True)
    (d / "busquedas.json").write_text(json.dumps({"_nota": "x", "busquedas": [
        {"slug": "prs-se-custom-24", "consulta": "prs se custom 24", "categoria": "guitarra", "precio_max": 3500, "paginas": 1},
    ]}), encoding="utf-8")
    return d


def seguidas(d):
    b = json.loads((d / "busquedas.json").read_text(encoding="utf-8"))["busquedas"]
    return [x for x in b if x["slug"] == interes.SLUG]


def test_agregar_desde_el_formulario_de_github(tmp_path):
    d = datos(tmp_path)
    msg = interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, HOY)
    assert "PRS SE Custom 24" in msg
    s = seguidas(d)[0]["seguir"]
    assert s == [{"id": "103081848", "marca": "PRS", "modelo": "SE Custom 24", "categoria": "guitarra",
                  "desde": "2026-11-19", "nota": "Sondeo de mercado; sin promesa de compra"}]
    cap = json.loads((d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8"))
    p = cap["publicaciones"][0]
    assert p["anuncio"] == "live" and p["precio_usd"] == 500 and p["foto"] == FOTO
    assert p["historial"] == [{"fecha": "2026-11-19", "estado": "live", "precio_usd": 500.0}]
    # repetirla no la duplica
    interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, HOY)
    assert len(seguidas(d)[0]["seguir"]) == 1
    # las demás búsquedas se conservan
    assert json.loads((d / "busquedas.json").read_text(encoding="utf-8"))["busquedas"][0]["slug"] == "prs-se-custom-24"


def test_quitar_desde_el_formulario(tmp_path):
    d = datos(tmp_path)
    interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, HOY)
    msg = interes.desde_issue(d, "Quitar de interés: reverb 103081848", "", HOY)
    assert "Quité" in msg and seguidas(d)[0]["seguir"] == []
    cap = json.loads((d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8"))
    assert cap["publicaciones"] == []


def test_titulo_desconocido_no_cambia_nada(tmp_path):
    d = datos(tmp_path)
    antes = (d / "busquedas.json").read_text(encoding="utf-8")
    assert interes.desde_issue(d, "Hola", CUERPO, HOY) is None
    assert (d / "busquedas.json").read_text(encoding="utf-8") == antes


def test_captura_diaria_sigue_precio_y_estado(tmp_path):
    d = datos(tmp_path)
    interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, date(2026, 11, 17))
    fila = ["103081848", "PRS SE Custom 24 2017 - 2019 - Whale Blue", 480, "good", 1, "2026-10-19", 0, "s--x--/a.jpg", "live"]
    armar([{"slug": interes.SLUG, "estado": "ok", "filas": [fila]}], {}, d, date(2026, 11, 18))  # sin modelo asignado
    armar([{"slug": interes.SLUG, "estado": "ok", "filas": [fila]}], {}, d, date(2026, 11, 19))  # sin cambios
    vendida = fila[:8] + ["sold"]
    armar([{"slug": interes.SLUG, "estado": "ok", "filas": [vendida]}], {}, d, date(2026, 11, 20))
    cap = json.loads((d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8"))
    p = cap["publicaciones"][0]
    assert p["marca"] == "PRS" and p["modelo"] == "SE Custom 24" and p["anuncio"] == "sold"
    assert [(h["fecha"], h["estado"], h["precio_usd"]) for h in p["historial"]] == [
        ("2026-11-17", "live", 500.0), ("2026-11-18", "live", 480.0), ("2026-11-20", "sold", 480.0)]
    assert p["revisada"] == "2026-11-20" and p["en_interes"]["desde"] == "2026-11-17"
    # vendida: no se evalúa ni cuenta como comparable
    pares, precios = leer_captura(d / "capturas" / "reverb-en-interes.json")
    assert pares == [] and precios == []


def test_si_la_lectura_falla_se_conserva_la_anterior(tmp_path):
    d = datos(tmp_path)
    interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, HOY)
    antes = (d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8")
    armar([{"slug": interes.SLUG, "estado": "HTTP 403", "filas": []}], {}, d, date(2026, 11, 20))
    armar([{"slug": interes.SLUG, "estado": "ok", "filas": []}], {}, d, date(2026, 11, 20))  # no vino la fila
    p = json.loads((d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8"))["publicaciones"][0]
    assert p["anuncio"] == "live" and len(p["historial"]) == 1 and json.loads(antes)["publicaciones"][0]["precio_usd"] == 500


def test_no_encontrada_se_marca_sin_borrar_datos(tmp_path):
    d = datos(tmp_path)
    interes.desde_issue(d, "En interés: reverb 103081848", CUERPO, HOY)
    armar([{"slug": interes.SLUG, "estado": "ok", "filas": [["103081848", "", 0, "", 0, "", 0, "", "no-encontrada"]]}],
          {}, d, date(2026, 11, 20))
    p = json.loads((d / "capturas" / "reverb-en-interes.json").read_text(encoding="utf-8"))["publicaciones"][0]
    assert p["anuncio"] == "no-encontrada" and p["precio_usd"] == 500 and p["titulo"].startswith("PRS SE Custom 24")
