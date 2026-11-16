from pytest import approx

from radar.costing import costo_puesto, flete_maximo, ingreso_neto, margen
from tests.conftest import P


def test_costo_puesto():
    c = costo_puesto(500, 30, 3270, P)
    assert c.base_cop == approx(1_882_233.255)
    assert c.arancel_cop == approx(188_223.3255)
    assert c.total_cop == approx(2_463_843.3308)


def test_flete_maximo_y_margen():
    ing = ingreso_neto(4_000_000, P)
    fm = flete_maximo(ing, 2_463_843.3308, P)
    assert fm == approx(736_156.6692)
    assert margen(ing, 2_463_843.3308, fm) == approx(0.25)


def test_flete_maximo_negativo_si_no_hay_margen():
    assert flete_maximo(2_000_000, 2_463_843.33, P) < 0


def test_comision_de_canal_reduce_ingreso():
    assert ingreso_neto(1_000_000, {**P, "comision_canal": 0.155}) == approx(845_000)
