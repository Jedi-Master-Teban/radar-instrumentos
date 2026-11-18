from pytest import approx

from radar.costing import cuenta, flete_maximo, precio_techo, venta
from tests.conftest import P

TRM = 3316.7
# Parámetros de los escenarios del 17 nov: flete de casillero US$200 por guitarra
Q = {**P, "flete_supuesto_usd": {**P["flete_supuesto_usd"], "guitarra": 200}}


def test_les_paul_2011_coincide_con_los_escenarios():
    c = cuenta(751, 100, "guitarra", TRM, Q)
    assert round(c.total_cop, -3) == 5_130_000
    v = venta(6_454_000, c, 0.05, Q)
    assert round(v.neto_cop, -3) == 1_001_000
    assert v.neto_usd == approx(v.neto_cop / TRM)
    assert v.margen == approx(v.neto_cop / c.total_cop)
    assert v.comision_cop == approx(322_700)


def test_cada_linea_trae_dolares_y_pesos_y_suman_el_total():
    c = cuenta(751, 100, "guitarra", TRM, Q)
    conceptos = [l.concepto for l in c.lineas]
    assert conceptos == ["Precio y envío en EE. UU.", "Impuesto de ventas en EE. UU.", "Flete, seguro e inspección",
                         "Recargo de la tarjeta", "Arancel", "IVA", "Ajuste del luthier"]
    for l in c.lineas:
        assert l.cop == approx(l.usd * TRM)
    assert sum(l.cop for l in c.lineas) == approx(c.total_cop)
    assert sum(l.usd for l in c.lineas) == approx(c.total_usd)
    assert c.lineas[0].usd == 851 and c.lineas[-1].cop == 150_000


def test_arancel_e_iva_se_cobran_sobre_producto_flete_y_seguro():
    c = cuenta(751, 100, "guitarra", TRM, Q)
    seguro = 0.035 * 851
    cif = 851 + 200 + seguro
    assert c.lineas[4].usd == approx(cif * 0.10)
    assert c.lineas[5].usd == approx(cif * 1.10 * 0.19)
    assert c.lineas[2].usd == approx(200 + seguro + 10)


def test_seguro_minimo_en_articulos_baratos():
    c = cuenta(100, 0, "pedal", TRM, Q)
    assert c.lineas[2].usd == approx(25 + 10 + 10)  # flete del pedal + seguro mínimo + inspección


def test_techo_deja_el_margen_objetivo_con_la_comision():
    for com in (0, 0.05, 0.10):
        t = precio_techo(6_454_000, 100, "guitarra", TRM, Q, com)
        v = venta(6_454_000, cuenta(t, 100, "guitarra", TRM, Q), com, Q)
        assert v.margen == approx(0.25, abs=1e-6)
    assert precio_techo(6_454_000, 100, "guitarra", TRM, Q, 0.10) < precio_techo(6_454_000, 100, "guitarra", TRM, Q, 0)


def test_techo_negativo_si_ni_regalada_hay_margen():
    assert precio_techo(300_000, 0, "guitarra", TRM, Q, 0.05) < 0


def test_flete_maximo_deja_el_margen_objetivo():
    fm = flete_maximo(6_454_000, 751, 100, "guitarra", TRM, Q, 0.05)
    q = {**Q, "flete_supuesto_usd": {**Q["flete_supuesto_usd"], "guitarra": fm}}
    v = venta(6_454_000, cuenta(751, 100, "guitarra", TRM, q), 0.05, q)
    assert v.margen == approx(0.25, abs=1e-6)
