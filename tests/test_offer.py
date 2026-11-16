from pytest import approx

from radar.costing import costo_puesto, margen
from radar.models import Oferta, ValoracionUS
from radar.offer import precio_techo, proponer
from tests.conftest import P


def test_techo_cumple_margen_objetivo():
    t = precio_techo(4_000_000, 30, "guitarra", 3270, P)
    c = costo_puesto(t, 30, 3270, P)
    assert margen(4_000_000, c.total_cop, 120 * 3270) == approx(0.25)


def test_proponer():
    o = proponer(600, 520, ValoracionUS(480, 430, 540, 8, 900))
    assert o == Oferta(techo_usd=520, apertura_usd=approx(408.0), retiro_usd=480)


def test_proponer_none_si_la_brecha_es_excesiva():
    assert proponer(1000, 500, ValoracionUS(900, 800, 950, 6, None)) is None


def test_proponer_sin_techo_usa_mercado_us():
    o = proponer(800, None, ValoracionUS(1900, 1700, 2100, 6, 2600))
    assert o.retiro_usd == 800 and o.apertura_usd == approx(680.0)


def test_techo_negativo_no_propone():
    assert proponer(500, -50, ValoracionUS(480, 430, 540, 8, None)) is None
