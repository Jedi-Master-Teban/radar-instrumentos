from radar.collectors.base import LectorBloqueado
from radar.models import Normalizado, PrecioTienda


class ModeloFalso:
    def __init__(self, normalizado="auto", estado="excelente", senales=()):
        self.normalizado, self.estado, self.senales = normalizado, estado, list(senales)
        self.mensajes = 0

    def normalizar(self, titulo, descripcion):
        if self.normalizado is None:
            return None
        partes = titulo.split()
        return Normalizado(marca=partes[0], modelo=" ".join(partes[1:3]), categoria="guitarra",
                           estado=self.estado, senales_motivado=list(self.senales))

    def mismo_articulo(self, objetivo, candidatos):
        return ["accesorio" not in c.lower() for c in candidatos]

    def mensaje_oferta(self, l, n, o, val):
        self.mensajes += 1
        return f"Would you accept ${o.apertura_usd:,.0f}?"


class Contador:
    """Fuente de precios falsa que cuenta sus llamadas."""

    def __init__(self, items=(), error=None):
        self.items, self.error, self.llamadas = list(items), error, 0

    def __call__(self, consulta, condicion=None):
        self.llamadas += 1
        if self.error:
            raise self.error
        return [i for i in self.items if condicion is None or i.condicion == condicion]


def us(usado=900, nuevo=1200, n=4):
    return Contador([PrecioTienda("reverb", "Fender Player Strat", usado, "usado") for _ in range(n)]
                    + [PrecioTienda("gc", "Fender Player Strat", nuevo, "nuevo")])


def co(usado=4_400_000, n=3, nuevo=None):
    items = [PrecioTienda("meli", "Fender Player Strat", usado, "usado") for _ in range(n)]
    if nuevo:
        items.append(PrecioTienda("Ortizo", "Fender Player Strat", nuevo, "nuevo"))
    return Contador(items)


BLOQUEO = LectorBloqueado("bloqueado")
