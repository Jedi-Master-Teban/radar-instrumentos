import httpx
import pytest

from radar import db
from radar.trm import trm_hoy


def cliente(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_trm_ok(con):
    c = cliente(lambda req: httpx.Response(200, json=[{"valor": "3270.15"}]))
    assert trm_hoy(con, c) == 3270.15


def _falla(req):
    raise httpx.ConnectError("sin red")


def test_trm_respaldo_manual(con):
    db.set_parametro(con, "trm_manual", 3300)
    assert trm_hoy(con, cliente(_falla)) == 3300


def test_trm_sin_red_ni_manual(con):
    with pytest.raises(RuntimeError):
        trm_hoy(con, cliente(_falla))


def test_trm_respuesta_vacia_usa_manual(con):
    db.set_parametro(con, "trm_manual", 3300)
    assert trm_hoy(con, cliente(lambda req: httpx.Response(200, json=[]))) == 3300
