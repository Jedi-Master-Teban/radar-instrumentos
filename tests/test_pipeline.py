import json

from pytest import approx

from radar import db
from radar.notify import SinAvisos
from radar.pipeline import correr
from tests.conftest import HOY, listing
from tests.fakes import BLOQUEO, Contador, ModeloFalso, co, us

TRM = 3270


def solo_una_consulta(con):
    con.execute("update watchlist set activo=0")
    con.execute("update watchlist set activo=1 where consulta='Fender electric guitar'")
    con.commit()


def lector(*ls):
    return lambda consulta: list(ls)


def ejecutar(con, lectores, fuentes_co=None, modelo=None, fuentes_us=None, avisos=None, hoy=HOY):
    solo_una_consulta(con)
    avisos = avisos or SinAvisos()
    r = correr(con, lectores, fuentes_us or {"reverb": us()}, {"meli": co()} if fuentes_co is None else fuentes_co,
               modelo or ModeloFalso(), avisos, TRM, hoy)
    return r, avisos


def test_oportunidad_con_margen_se_alerta(con):
    r, av = ejecutar(con, {"ebay": lector(listing(500))})
    assert r["oportunidades"] == 1 and r["alertas"] == 1
    op = av.alertas[0]
    assert op["tipo"] == "reventa" and op["margen_en_retiro"] >= 0.25
    assert op["oferta"]["retiro_usd"] == 500 and op["oferta"]["apertura_usd"] == approx(425.0)
    assert op["precio_co_cop"] == approx(3_960_000) and op["mensaje"]


def test_sin_margen_no_se_alerta(con):
    r, av = ejecutar(con, {"ebay": lector(listing(790))}, fuentes_co={"meli": co(usado=2_000_000)})
    assert r["oportunidades"] == 0 and av.alertas == []


def test_ganga_sin_referencia_en_colombia_no_se_descarta(con):
    # Strandberg a 800 con usados en EE. UU. a ~1.710: no existe en Colombia y aun así se alerta
    r, av = ejecutar(con, {"facebook": lector(listing(800, plataforma="facebook", titulo="Strandberg Boden Plini"))},
                     fuentes_co={"meli": Contador([])}, fuentes_us={"reverb": us(usado=1900, nuevo=2600)})
    assert r["alertas"] == 1
    op = av.alertas[0]
    assert op["tipo"] == "ganga" and op["descuento_us"] == approx(1 - 800 / 1710)
    assert any("inusualmente bajo" in b for b in op["banderas"])


def test_sin_referencia_co_y_sin_descuento_no_se_alerta(con):
    r, av = ejecutar(con, {"ebay": lector(listing(700))}, fuentes_co={"meli": Contador([])})
    assert r["alertas"] == 0 and r["detalle"] == {"sin_margen": 1}


def test_reventa_estimada_desde_precio_nuevo_de_tienda(con):
    r, av = ejecutar(con, {"ebay": lector(listing(500))}, fuentes_co={"ortizo": co(n=0, nuevo=6_000_000)})
    op = av.alertas[0]
    assert op["tipo"] == "reventa" and op["precio_co_cop"] == approx(4_200_000)
    assert any("estimado desde el nuevo" in b for b in op["banderas"])


def test_fuera_del_rango_de_precio_nuevo(con):
    r, _ = ejecutar(con, {"ebay": lector(listing(300))}, fuentes_us={"reverb": us(usado=400, nuevo=450)})
    assert r["detalle"] == {"fuera_de_rango": 1}


def test_estado_regular_se_descarta(con):
    r, _ = ejecutar(con, {"ebay": lector(listing(500))}, modelo=ModeloFalso(estado="regular"))
    assert r["detalle"] == {"descartado_estado": 1}


def test_maximo_cinco_alertas_las_de_mayor_puntaje(con):
    ls = [listing(380 + 10 * i, id_externo=f"A{i}") for i in range(8)]
    r, av = ejecutar(con, {"ebay": lector(*ls)})
    assert r["oportunidades"] == 8 and len(av.alertas) == 5
    assert sorted(a["listing"]["precio_usd"] for a in av.alertas) == [380, 390, 400, 410, 420]


def test_lector_bloqueado_no_detiene_la_corrida(con):
    def ebay(consulta):
        raise BLOQUEO
    r, av = ejecutar(con, {"ebay": ebay, "reverb": lector(listing(500, plataforma="reverb"))})
    assert r["alertas"] == 1 and r["errores"] == 1
    assert any("lector_bloqueado: ebay" in a for a in av.avisos)


def test_lector_sin_resultados_avisa(con):
    r, av = ejecutar(con, {"ebay": lector()})
    assert av.avisos == ["lector_sin_resultados: ebay — puede haber cambiado el diseño del sitio"]
    assert con.execute("select count(*) from eventos where tipo='lector_sin_resultados'").fetchone()[0] == 1


def test_no_realerta_la_misma_publicacion(con):
    ejecutar(con, {"ebay": lector(listing(500))})
    r, av = ejecutar(con, {"ebay": lector(listing(500))})
    assert r["alertas"] == 0 and r["nuevos_o_rebajados"] == 0


def test_rebaja_agrega_senal_y_realerta(con):
    ejecutar(con, {"ebay": lector(listing(520))})
    r, av = ejecutar(con, {"ebay": lector(listing(480))})
    assert r["alertas"] == 1 and "rebajado" in av.alertas[0]["senales"]
    assert con.execute("select count(*) from oportunidades").fetchone()[0] == 1


def test_sin_normalizar_continua(con):
    r, _ = ejecutar(con, {"ebay": lector(listing(500), listing(510, id_externo="B2"))}, modelo=ModeloFalso(normalizado=None))
    assert r["detalle"] == {"sin_normalizar": 2} and r["errores"] == 0


def test_solo_recogida_local_y_precios_absurdos_no_entran(con):
    r, _ = ejecutar(con, {"ebay": lector(listing(500, hace_envios=False), listing(20, id_externo="B"),
                                         listing(9000, id_externo="C"))})
    assert r["listings"] == 0


def test_error_en_una_publicacion_no_tumba_las_demas(con):
    class Roto(ModeloFalso):
        def normalizar(self, titulo, descripcion):
            if "ROTO" in titulo:
                raise ValueError("boom")
            return super().normalizar(titulo, descripcion)
    r, av = ejecutar(con, {"ebay": lector(listing(500, titulo="Fender ROTO x"), listing(500, id_externo="B"))}, modelo=Roto())
    assert r["alertas"] == 1 and r["errores"] == 1 and r["detalle"]["error"] == 1


def test_resumen_queda_en_eventos(con):
    ejecutar(con, {"ebay": lector(listing(500))})
    d = json.loads(con.execute("select detalle from eventos where tipo='corrida'").fetchone()[0])
    assert d["alertas"] == 1
