import httpx

from radar.notify import SinAvisos, Telegram, cop, formato_alerta, usd
from radar.pipeline import correr
from tests.conftest import HOY, listing
from tests.fakes import ModeloFalso, co, us


def una_alerta(con):
    con.execute("update watchlist set activo=0")
    con.execute("update watchlist set activo=1 where consulta='Fender electric guitar'")
    av = SinAvisos()
    correr(con, {"ebay": lambda c: [listing(500, fotos=["https://i.ebayimg.com/x.webp"])]}, {"r": us()}, {"m": co()},
           ModeloFalso(), av, 3270, HOY)
    return av.alertas[0]


def test_formatos():
    assert cop(2_880_000) == "$2.880.000" and cop(736_156.67) == "$736.157" and usd(408) == "US$408" and cop(None) == "—"


def test_formato_alerta(con):
    t = formato_alerta(una_alerta(con))
    for esperado in ["REVENTA", "Apertura: US$425", "Retiro: US$500", "Colombia usado: $4.950.000 (3 refs)",
                     "EE. UU. usado: US$810 (4 refs)", "Costo puesto en Bogotá: US$", "Flete máximo:",
                     "https://www.ebay.com/itm/A1", "<pre>Would you accept $425?</pre>"]:
        assert esperado in t, esperado


def test_telegram_envia_foto(con):
    vistos = []

    def handler(req):
        vistos.append((req.url.path, req.read().decode()))
        return httpx.Response(200, json={"ok": True})
    tg = Telegram("TOKEN", "42", httpx.Client(transport=httpx.MockTransport(handler)))
    tg.alerta(una_alerta(con))
    assert vistos[0][0] == "/botTOKEN/sendPhoto" and '"chat_id":"42"' in vistos[0][1].replace(" ", "")


def test_telegram_error_no_lanza_y_se_registra(con):
    registro = []
    tg = Telegram("T", "1", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400))),
                  registrar=lambda t, d: registro.append((t, d)))
    tg.alerta(una_alerta(con))
    tg.aviso("hola")
    assert len(registro) == 3 and registro[0][0] == "telegram_error"  # foto, mensaje de respaldo y aviso
