import json
from types import SimpleNamespace

from radar.llm import Modelo
from radar.models import Normalizado, Oferta, ValoracionUS
from tests.conftest import listing


class ClienteFalso:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._crear))

    def _crear(self, **kw):
        self.llamadas += 1
        r = self.respuestas[min(self.llamadas - 1, len(self.respuestas) - 1)]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])


OK = json.dumps({"marca": "Fender", "modelo": "Player Stratocaster", "anio": 2021, "categoria": "guitarra",
                 "estado": "excelente", "defectos": [], "modificaciones": [], "senales_motivado": ["must sell"]})
N = Normalizado("Fender", "Player Stratocaster", "guitarra", "excelente")
VAL = ValoracionUS(480, 430, 540, 8, 900)
OF = Oferta(520, 408.0, 480)


def test_normalizar_ok():
    n = Modelo(ClienteFalso(OK)).normalizar("t", "d")
    assert (n.marca, n.modelo, n.categoria, n.estado, n.anio) == ("Fender", "Player Stratocaster", "guitarra", "excelente", 2021)
    assert n.senales_motivado == ["must sell"]


def test_normalizar_acepta_bloque_de_codigo():
    assert Modelo(ClienteFalso("```json\n" + OK + "\n```")).normalizar("t", "d") is not None


def test_normalizar_json_invalido_reintenta_una_vez():
    c = ClienteFalso("no soy json")
    assert Modelo(c).normalizar("t", "d") is None and c.llamadas == 2


def test_normalizar_estado_fuera_de_escala():
    assert Modelo(ClienteFalso(OK.replace("excelente", "mint"))).normalizar("t", "d") is None


def test_normalizar_error_de_red():
    assert Modelo(ClienteFalso(RuntimeError("timeout"))).normalizar("t", "d") is None


def test_mismo_articulo():
    assert Modelo(ClienteFalso("[true, false]")).mismo_articulo(N, ["a", "b"]) == [True, False]
    assert Modelo(ClienteFalso("[true]")).mismo_articulo(N, ["a", "b"]) == [False, False]  # longitud distinta
    assert Modelo(ClienteFalso("x")).mismo_articulo(N, []) == []


def test_mensaje_valido_se_usa():
    m = Modelo(ClienteFalso("Hi, would you take $408? Similar ones list at $430-$540.")).mensaje_oferta(listing(), N, OF, VAL)
    assert "$408" in m


def test_mensaje_que_inventa_compradores_se_reemplaza():
    m = Modelo(ClienteFalso("I have another buyer but would pay $408")).mensaje_oferta(listing(), N, OF, VAL)
    assert "$408" in m and "another buyer" not in m


def test_mensaje_sin_el_monto_se_reemplaza():
    assert "$408" in Modelo(ClienteFalso("How about a discount?")).mensaje_oferta(listing(), N, OF, VAL)
