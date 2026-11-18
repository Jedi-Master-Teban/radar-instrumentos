from radar.db import guardar_listing, parametros, rebajas, set_parametro
from tests.conftest import listing


def test_guardar_listing_nuevo_y_duplicado(con):
    id1, cambio1 = guardar_listing(con, listing(precio=500))
    id2, cambio2 = guardar_listing(con, listing(precio=500))
    assert id1 == id2 and cambio1 is True and cambio2 is False


def test_rebaja_actualiza_y_guarda_historial(con):
    lid, _ = guardar_listing(con, listing(precio=500))
    _, cambio = guardar_listing(con, listing(precio=450))
    assert cambio is True
    assert [r[0] for r in con.execute("select precio_usd from historial_precios order by id")] == [500, 450]
    assert con.execute("select count(*) from listings").fetchone()[0] == 1
    assert rebajas(con, lid) == 1


def test_parametros_por_defecto(con):
    p = parametros(con)
    assert p["arancel"] == 0.10 and p["iva"] == 0.19 and p["max_alertas_dia"] == 5
    assert p["flete_supuesto_usd"]["guitarra"] == 200 and p["comision_canal"] == 0.05
    assert p["precio_nuevo_min_usd"] == 600 and p["precio_nuevo_max_usd"] == 3500


def test_set_parametro_persiste(con):
    set_parametro(con, "margen_objetivo", 0.30)
    assert parametros(con)["margen_objetivo"] == 0.30


def test_watchlist_semilla_incluye_las_ocho_marcas(con):
    marcas = {r[0] for r in con.execute("select marca from watchlist where categoria='guitarra'")}
    assert marcas == {"Gibson", "Fender", "Jackson", "PRS", "Strandberg", "Schecter",
                      "Ernie Ball Music Man", "Epiphone"}


def test_migracion_amplia_ciudades_solo_si_no_se_cambiaron(tmp_path):
    from radar import db
    ruta = str(tmp_path / "r.db")
    c = db.conectar(ruta)
    db.set_parametro(c, "ciudades_fb", ["miami", "nyc"])
    c.close()
    assert len(db.parametros(db.conectar(ruta))["ciudades_fb"]) == 24
    c = db.conectar(ruta)
    db.set_parametro(c, "ciudades_fb", ["tampa"])
    c.close()
    assert db.parametros(db.conectar(ruta))["ciudades_fb"] == ["tampa"]
