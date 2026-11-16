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
    return TestClient(crear_app(aj)), aj


def test_lista_muestra_reventa_y_ganga(cliente):
    c, _ = cliente
    r = c.get("/")
    assert r.status_code == 200 and "Fender Player Stratocaster" in r.text and "Strandberg Boden Plini" in r.text
    assert "sin referencia" in r.text


def test_filtro_por_tipo(cliente):
    c, _ = cliente
    r = c.get("/?tipo=ganga")
    assert "Strandberg" in r.text and "Fender Player" not in r.text


def test_detalle_y_cambio_de_estado(cliente):
    c, _ = cliente
    assert "Mensaje de oferta" in c.get("/oportunidad/1").text
    assert c.post("/oportunidad/1/estado", data={"estado": "ofertada"}, follow_redirects=False).status_code == 303
    assert "Fender Player" not in c.get("/").text and "Fender Player" in c.get("/?estado=ofertada").text
    assert c.post("/oportunidad/1/estado", data={"estado": "robada"}).status_code == 422
    assert c.get("/oportunidad/999").status_code == 404


def test_detalle_de_ganga_explica_que_no_esta_en_colombia(cliente):
    c, _ = cliente
    t = c.get("/oportunidad/2").text
    assert "no aparece en Colombia" in t and "inusualmente bajo" in t


def test_flete_real_recalcula_margen(cliente):
    c, _ = cliente
    c.post("/oportunidad/1/flete", data={"flete_real_cop": "900000"})
    assert "Margen con flete real: <b>18 %</b>" in c.get("/oportunidad/1").text
    assert c.post("/oportunidad/1/flete", data={"flete_real_cop": "-5"}).status_code == 422


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
    c = TestClient(crear_app(aj, lanzar=lanzar, vivo=lambda pid: pid in vivos))
    assert "ninguna corrida" in c.get("/").text  # lista vacía explica qué hacer
    assert "Aún no hay registro" in c.get("/corrida").text
    assert c.post("/corrida", data={"modo": "prueba"}, follow_redirects=False).status_code == 303
    t = c.get("/corrida").text
    assert "corrida en curso" in t and "ebay: 12 publicaciones" in t
    c.post("/corrida", data={"modo": "completa"})  # ya hay una: no lanza otra
    assert lanzadas == [True]
    vivos.clear()
    assert "Corrida completa" in c.get("/corrida").text
    assert c.post("/corrida", data={"modo": "otra"}).status_code == 422
