import pytest
from fastapi.testclient import TestClient

from radar import config, db
from radar.notify import SinAvisos
from radar.pipeline import correr
from radar.web.app import crear_app
from tests.conftest import HOY, listing
from tests.fakes import Contador, ModeloFalso, co, us


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    for k in config.CLAVES_SECRETAS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("RADAR_HOME", str(tmp_path))
    aj = config.cargar(None)
    con = db.conectar(aj.ruta_db)
    con.execute("update watchlist set activo=0")
    con.execute("update watchlist set activo=1 where consulta='Fender electric guitar'")
    correr(con, {"ebay": lambda c: [listing(500)]}, {"r": us()}, {"m": co()}, ModeloFalso(), SinAvisos(), 3270, HOY)
    con.execute("update watchlist set consulta='zz', activo=0 where consulta='Fender electric guitar'")
    con.execute("insert into watchlist(categoria, marca, consulta) values('guitarra','Strandberg','sb')")
    con.commit()
    correr(con, {"facebook": lambda c: [listing(800, id_externo="F9", plataforma="facebook", titulo="Strandberg Boden Plini")]},
           {"r": us(usado=1900, nuevo=2600)}, {"m": Contador([])}, ModeloFalso(), SinAvisos(), 3270, HOY)
    con.close()
    return TestClient(crear_app(aj, carpeta_capturas=tmp_path / 'capturas')), aj


def test_hoy_muestra_lista_y_estuche_en_dos_monedas(cliente):
    c, _ = cliente
    r = c.get("/")
    assert r.status_code == 200 and "Player Stratocaster" in r.text and "Boden Plini" in r.text
    assert 'chip reventa">Reventa' in r.text and 'chip ganga">Ganga' in r.text and "Referencia de Colombia estimada" in r.text
    assert r.text.count('data-op="') == 2 and r.text.count('data-panel="') == 2 and 'href="/oportunidad/1"' in r.text
    # una cifra por comisión, en pesos y dólares
    for k in ("0", "5", "10"):
        assert f'class="esc dinero" data-c="{k}"' in r.text and f'data-elegir-com="{k}"' in r.text
    assert "A dónde va cada peso de la venta" in r.text and ">USD<" in r.text and ">COP<" in r.text and "US$" in r.text


def test_explorar_trae_todo_para_filtrar(cliente):
    c, _ = cliente
    t = c.get("/explorar").text
    assert 'data-clase="ganga"' in t and 'data-clase="reventa"' in t and "Solo oportunidades" in t
    assert 'data-marca="Strandberg"' in t and 'aria-current="page">Explorar' in t
    assert 'data-neto5="' in t and 'data-neto10="' in t and "Neto al precio pedido" in t


def test_detalle_y_cambio_de_estado(cliente):
    c, _ = cliente
    t = c.get("/oportunidad/1").text
    assert "Mensaje de oferta" in t and "Con tus números" in t and "Publica en" in t and "cuentasRadar" in t
    assert c.post("/oportunidad/1/estado", data={"estado": "ofertada"}, follow_redirects=False).status_code == 303
    assert '<span class="chip">Ofertada</span>' in c.get("/oportunidad/1").text
    assert c.post("/oportunidad/1/estado", data={"estado": "robada"}).status_code == 422
    assert c.get("/oportunidad/999").status_code == 404


def test_detalle_de_ganga_explica_que_no_esta_en_colombia(cliente):
    c, _ = cliente
    t = c.get("/oportunidad/2").text
    assert "No aparece en las tiendas consultadas" in t and "es una estimación" in t and "inusualmente bajo" in t


def test_flete_real_mueve_el_techo_y_se_guarda(cliente):
    c, _ = cliente
    antes = c.get("/oportunidad/1").text
    assert 'id="i-flete" min="0" step="5" inputmode="decimal" value="200"' in antes
    c.post("/oportunidad/1/flete", data={"flete_real_usd": "260"})
    t = c.get("/oportunidad/1").text
    assert 'id="i-flete" min="0" step="5" inputmode="decimal" value="260"' in t
    assert '"flete": 200' in t  # el radar conserva su supuesto; el navegador recalcula con el flete guardado
    assert c.post("/oportunidad/1/flete", data={"flete_real_usd": "-5"}).status_code == 422


def test_parametros(cliente):
    c, aj = cliente
    assert c.post("/parametros", data={"margen_objetivo": "0.30", "flete_guitarra": "140"}, follow_redirects=False).status_code == 303
    p = db.parametros(db.conectar(aj.ruta_db))
    assert p["margen_objetivo"] == 0.30 and p["flete_supuesto_usd"]["guitarra"] == 140 and p["flete_supuesto_usd"]["pedal"] == 25
    assert c.post("/parametros", data={"margen_objetivo": "abc"}).status_code == 422
    assert c.post("/parametros", data={"tiendas_co": '[{"nombre":"X","origen":"http://x","plataforma":"otra"}]'}).status_code == 422


def test_watchlist_y_referencia_manual(cliente):
    c, aj = cliente
    c.post("/watchlist", data={"categoria": "pedal", "marca": "MXR", "consulta": "MXR Phase 90"})
    c.post("/referencia", data={"marca": "Fender", "modelo": "Player Stratocaster", "usado_cop": "3500000"})
    t = c.get("/watchlist").text
    assert "MXR Phase 90" in t and "$3.500.000" in t and "manual" in t
    assert c.post("/watchlist", data={"categoria": "piano", "marca": "x", "consulta": "y"}).status_code == 422


def test_ajustes_guarda_claves_sin_mostrarlas(cliente):
    c, aj = cliente
    c.post("/ajustes", data={"nim_api_key": "nvapi-SECRETO", "nim_model": "meta/modelo"})
    env = (aj.home / ".env")
    assert "NIM_API_KEY=nvapi-SECRETO" in env.read_text() and oct(env.stat().st_mode)[-3:] == "600"
    t = c.get("/ajustes").text
    assert "nvapi-SECRETO" not in t and "configurada" in t and "meta/modelo" in t
    c.post("/ajustes", data={"nim_api_key": "", "telegram_chat_id": "42"})  # vacío conserva
    assert "NIM_API_KEY=nvapi-SECRETO" in env.read_text() and "TELEGRAM_CHAT_ID=42" in env.read_text()


def test_eventos(cliente):
    c, _ = cliente
    assert "corrida" in c.get("/eventos").text


def test_formulario_desde_otro_sitio_se_rechaza(cliente):
    c, aj = cliente
    r = c.post("/ajustes", data={"nim_api_key": "robada"}, headers={"Origin": "https://sitio-malicioso.example"})
    assert r.status_code == 403 and not (aj.home / ".env").exists()


def test_corrida_desde_el_tablero(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_HOME", str(tmp_path))
    aj = config.cargar(None)
    lanzadas, vivos = [], set()

    def lanzar(a, prueba):
        lanzadas.append(prueba)
        vivos.add(4242)
        (a.home / "corrida.log").write_text("ebay: 12 publicaciones\n")
        return 4242
    c = TestClient(crear_app(aj, lanzar=lanzar, vivo=lambda pid: pid in vivos, carpeta_capturas=tmp_path / 'capturas'))
    assert "Todavía no hay publicaciones evaluadas" in c.get("/").text  # lista vacía explica qué hacer
    assert "Aún no hay corridas" in c.get("/corrida").text
    assert c.post("/corrida", data={"modo": "prueba"}, follow_redirects=False).status_code == 303
    t = c.get("/corrida").text
    assert "corrida en curso" in t and "ebay: 12 publicaciones" in t
    c.post("/corrida", data={"modo": "completa"})  # ya hay una: no lanza otra
    assert lanzadas == [True]
    vivos.clear()
    assert "Corrida completa con NIM" in c.get("/corrida").text
    assert c.post("/corrida", data={"modo": "otra"}).status_code == 422


def test_proceso_terminado_no_cuenta_como_corrida_activa():
    import subprocess
    import sys
    import time

    from radar.web.app import _vivo
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    time.sleep(0.5)  # ya terminó, pero nadie lo ha recogido: antes se veía como "en curso"
    assert _vivo(proc.pid) is False


def test_tablero_importa_capturas_del_repo_al_abrir(tmp_path, monkeypatch):
    import json as js

    monkeypatch.setenv("RADAR_HOME", str(tmp_path))
    aj = config.cargar(None)
    con = db.conectar(aj.ruta_db)
    db.set_parametro(con, "trm_manual", 3316.7)  # sin red en las pruebas
    con.close()
    carpeta = tmp_path / "capturas"
    carpeta.mkdir()
    pubs = [{"id": str(i), "titulo": f"Strandberg Boden Prog NX 6 #{i}", "url": f"https://reverb.com/item/{i}",
             "precio_usd": pr, "marca": "Strandberg", "modelo": "Boden Prog NX 6", "estado": "excellent"}
            for i, pr in enumerate([1000, 1650, 1700, 1750])]
    pubs.append({"id": "9", "titulo": "Strandberg Boden Neck-Thru 6 #a", "url": "https://reverb.com/item/9", "precio_usd": 1700,
                 "marca": "Strandberg", "modelo": "Boden Prog NX 6", "estado": "good"})
    (carpeta / "a.json").write_text(js.dumps({"fuente": "reverb", "publicaciones": pubs}))
    c = TestClient(crear_app(aj, carpeta_capturas=carpeta))
    t = c.get("/").text
    assert 'href="https://reverb.com/item/0"' in t and 'chip ganga">Ganga' in t
    x = c.get("/explorar").text
    assert "Guitarras (5)" in x
    assert "A precio de mercado" in x and "Neck-thru" in x and "capturas importadas" in c.get("/corrida").text
