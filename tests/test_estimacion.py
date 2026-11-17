import json

from pytest import approx

from radar.models import Normalizado, PrecioTienda, ValoracionUS
from radar.valuation import ModeloPorPalabras, actualizar_colombia, estimar_co, sobreprecio_marca
from tests.conftest import HOY, P
from tests.fakes import Contador

N = Normalizado("Strandberg", "Boden Prog NX 6", "guitarra", "excelente")


def ref(con, marca, modelo, nuevo_cop, nuevo_usd):
    con.execute("insert into referencias_co(marca, modelo, nuevo_cop, n_usado, n_nuevo, fecha) values(?,?,?,0,1,?)",
                (marca, modelo, nuevo_cop, HOY.isoformat()))
    con.execute("insert into referencias_us(marca, modelo, datos, fecha) values(?,?,?,?)",
                (marca, modelo, json.dumps({"nuevo_usd": nuevo_usd}), HOY.isoformat()))


def test_paridad_de_importacion_cuando_no_hay_datos(con):
    precio, n, origen = estimar_co(con, N, ValoracionUS(1485, 1400, 1700, 7, 2599), 3270, P)
    assert origen == "estimado: paridad de importación del nuevo"
    assert precio == approx((2599 * 1.07 * 3270 * 1.015 * 1.1 * 1.19 + 120 * 3270) * 0.70)


def test_costo_de_traer_una_usada_si_no_hay_precio_nuevo(con):
    precio, _, origen = estimar_co(con, N, ValoracionUS(1485, 1400, 1700, 7, None), 3270, P)
    assert origen == "estimado: costo de traer una usada"
    assert precio == approx(1485 * 1.07 * 3270 * 1.015 * 1.1 * 1.19 + 120 * 3270)


def test_sobreprecio_de_la_marca_y_general(con):
    assert sobreprecio_marca(con, "Gibson", 3270) is None
    ref(con, "Gibson", "Les Paul Studio", 9_330_000, 1599)
    r = sobreprecio_marca(con, "Gibson", 3270)
    assert r[0] == approx(9_330_000 / (1599 * 3270)) and r[2] == "Gibson"
    assert sobreprecio_marca(con, "Strandberg", 3270) is None  # una sola marca no basta para generalizar
    ref(con, "Fender", "Player II", 5_000_000, 850)
    ref(con, "PRS", "SE Custom 24", 6_000_000, 899)
    ref(con, "X", "accesorio mal emparejado", 90_000, 2000)  # razón absurda: se ignora
    g = sobreprecio_marca(con, "Strandberg", 3270)
    assert g[2] == "todas las marcas" and g[1] == 3
    precio, _, origen = estimar_co(con, N, ValoracionUS(1485, 1400, 1700, 7, 2599), 3270, P)
    assert origen.startswith("estimado: sobreprecio de todas las marcas") and precio == approx(2599 * 3270 * g[0] * 0.70)


def test_modelo_por_palabras():
    m = ModeloPorPalabras()
    assert m.mismo_articulo(Normalizado("Gibson", "Les Paul Studio", "guitarra", "bueno"),
                            ["Guitarra Eléctrica GIBSON Les-Paul Studio Ebony", "Gibson Les Paul Standard", "Estuche Gibson"]) \
        == [True, False, False]
    assert m.mismo_articulo(Normalizado("Strandberg", "Sälen Jazz NX 6", "guitarra", "bueno"), ["strandberg salen jazz nx 6"]) == [True]


def test_actualizar_colombia_consulta_cada_modelo_y_fuerza_reimportar(con):
    from radar import db
    for i, modelo in enumerate(["Les Paul Studio", "SG Standard"]):
        con.execute("insert into oportunidades(listing_id, tipo, puntaje, datos) values(?,?,?,?)",
                    (i + 1, "observacion", 0, json.dumps({"normalizado": {"marca": "Gibson", "modelo": modelo, "categoria": "guitarra"}})))
    db.set_parametro(con, "capturas_importadas", {"a.json": 1})
    tienda = Contador([PrecioTienda("Ortizo", "Guitarra Gibson Les Paul Studio", 9_330_000, "nuevo")])
    r = actualizar_colombia(con, {"Ortizo": tienda}, HOY)
    assert r == {"modelos": 2, "con_precio_en_colombia": 1} and tienda.llamadas == 2
    assert con.execute("select nuevo_cop from referencias_co where modelo='Les Paul Studio'").fetchone()[0] == 9_330_000
    assert db.parametros(con)["capturas_importadas"] == {}


def test_modelo_por_palabras_respeta_el_orden():
    m = ModeloPorPalabras()
    objetivo = Normalizado("Fender", "Player Stratocaster HSS Plus Top", "guitarra", "bueno")
    assert m.mismo_articulo(objetivo, ["Guitarra Fender Player Plus Stratocaster HSS Tequila Sunrise",
                                       "Fender Player Stratocaster HSS Plus Top Tobacco Burst"]) == [False, True]

    assert m.mismo_articulo(Normalizado("Gibson", "Les Paul Studio", "guitarra", "bueno"),
                            ["Gibson Les Paul Modern Studio Electric Guitar", "Guitarra Gibson Les Paul Studio Ebony"]) == [False, True]
