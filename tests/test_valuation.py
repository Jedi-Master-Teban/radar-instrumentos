from datetime import timedelta

from pytest import approx

from radar import db
from radar.models import Normalizado, PrecioTienda, ReferenciaCO
from radar.valuation import (calcular_referencia_co, calcular_valoracion_us, fijar_referencia_manual,
                             precio_reventa_co, referencia_co, referencia_us)
from tests.conftest import HOY, P
from tests.fakes import BLOQUEO, Contador, ModeloFalso, co, us

N = Normalizado("Fender", "Player Stratocaster", "guitarra", "excelente")


def pt(precio, cond="usado", titulo="x"):
    return PrecioTienda("f", titulo, precio, cond)


def test_referencia_co_descuenta_usados_y_quita_atipicos():
    items = [pt(3_000_000), pt(3_200_000), pt(3_400_000), pt(80_000), pt(5_500_000, "nuevo")]
    r = calcular_referencia_co(items, HOY, P)
    assert r.usado_cop == approx(2_880_000) and r.n_usado == 3
    assert r.nuevo_cop == approx(5_500_000) and r.n_nuevo == 1  # el precio de tienda no se descuenta


def test_valoracion_us():
    v = calcular_valoracion_us([pt(800), pt(900), pt(1000), pt(1100), pt(30)], [pt(1500, "nuevo")], P)
    assert v.n == 4 and v.mediana_usd == approx(950 * 0.9) and v.nuevo_usd == 1500
    assert calcular_valoracion_us([pt(800), pt(900)], [], P) is None  # menos de 3 comparables


def test_precio_reventa_co():
    assert precio_reventa_co(ReferenciaCO(3e6, None, 3, 0, HOY), P) == (3e6, 3, "usados en Colombia")
    assert precio_reventa_co(ReferenciaCO(3e6, 5e6, 2, 1, HOY), P)[0] == approx(3.5e6)  # pocos usados → desde el nuevo
    assert precio_reventa_co(ReferenciaCO(None, None, 0, 0, HOY), P) is None
    assert precio_reventa_co(ReferenciaCO(3e6, None, 0, 0, HOY, True), P)[2] == "manual"


def test_cache_co_vigente_no_consulta(con):
    f = co()
    referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY - timedelta(days=3))
    referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY)
    assert f.llamadas == 1


def test_cache_co_vencida_consulta(con):
    f = co()
    referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY - timedelta(days=8))
    referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY)
    assert f.llamadas == 2


def test_bloqueo_devuelve_cache_vencida_y_registra(con):
    referencia_co(con, {"meli": co()}, ModeloFalso(), N, HOY - timedelta(days=8))
    ref, _ = referencia_co(con, {"meli": Contador(error=BLOQUEO)}, ModeloFalso(), N, HOY)
    assert ref.n_usado == 3
    assert con.execute("select count(*) from eventos where tipo='lector_bloqueado'").fetchone()[0] == 1


def test_referencia_manual_manda(con):
    fijar_referencia_manual(con, "Fender", "Player Stratocaster", 3_500_000, HOY)
    f = co()
    ref, _ = referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY + timedelta(days=30))
    assert ref.manual and ref.usado_cop == 3_500_000 and f.llamadas == 0


def test_accesorios_no_cuentan(con):
    f = Contador([pt(3_000_000, titulo="Fender"), pt(3_100_000, titulo="Fender"), pt(90_000, titulo="Correa accesorio")])
    ref, detalle = referencia_co(con, {"meli": f}, ModeloFalso(), N, HOY)
    assert ref.n_usado == 2 and len(detalle) == 2


def test_cache_us(con):
    f = us()
    v1, _ = referencia_us(con, {"reverb": f}, ModeloFalso(), N, HOY)
    v2, _ = referencia_us(con, {"reverb": f}, ModeloFalso(), N, HOY)
    assert v1 == v2 and v1.mediana_usd == approx(810) and f.llamadas == 2  # usado + nuevo, una sola vez
    assert db.parametros(con)["cache_us_dias"] == 7
