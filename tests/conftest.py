from datetime import date
from pathlib import Path

import pytest

from radar import db
from radar.models import Listing

FIX = Path(__file__).parent / "fixtures"
HOY = date(2026, 11, 15)
P = dict(db.PARAMETROS_DEFECTO)


def leer(nombre: str) -> str:
    return (FIX / nombre).read_text(encoding="utf-8")


def listing(precio=500.0, id_externo="A1", plataforma="ebay", **kw) -> Listing:
    base = dict(plataforma=plataforma, id_externo=id_externo, url=f"https://www.ebay.com/itm/{id_externo}",
                titulo="Fender Player Stratocaster 2021", precio_usd=precio, envio_us_usd=30.0,
                acepta_ofertas=True, hace_envios=True, descripcion="Great condition")
    base.update(kw)
    return Listing(**base)


@pytest.fixture
def con():
    c = db.conectar(":memory:")
    yield c
    c.close()
