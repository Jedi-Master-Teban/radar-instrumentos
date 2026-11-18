from pytest import approx

from radar.models import Oferta, ValoracionUS
from radar.offer import proponer


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
