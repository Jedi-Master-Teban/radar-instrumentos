"""Avisos por Telegram."""
from __future__ import annotations

import html

import httpx


def cop(x: float | None) -> str:
    return "—" if x is None else "$" + f"{round(x):,}".replace(",", ".")


def usd(x: float | None) -> str:
    return "—" if x is None else "US$" + f"{round(x):,}"


def formato_alerta(op: dict) -> str:
    l, n, v, r, o, c = (op["listing"], op["normalizado"], op["valoracion_us"], op["referencia_co"], op["oferta"],
                        op["costo"])
    e = html.escape
    lineas = [
        f"<b>{'REVENTA' if op['tipo'] == 'reventa' else 'GANGA (sin referencia en Colombia)'}</b> · {e(l['plataforma'])}",
        f"<b>{e(l['titulo'])}</b>",
        f"{e(n['marca'])} {e(n['modelo'])} · estado: {e(n['estado'])}",
        f"Precio pedido: {usd(l['precio_usd'])} (envío en EE. UU.: {usd(l['envio_us_usd'])})",
        f"Apertura: {usd(o['apertura_usd'])} · Techo: {usd(o['techo_usd'])} · Retiro: {usd(o['retiro_usd'])}",
        f"EE. UU. usado: {usd(v['mediana_usd'])} ({v['n']} refs) · nuevo: {usd(v['nuevo_usd'])}",
    ]
    if r.get("usado_cop") or r.get("nuevo_cop"):
        lineas.append(f"Colombia usado: {cop(r.get('usado_cop'))} ({r.get('n_usado', 0)} refs) · "
                      f"nuevo: {cop(r.get('nuevo_cop'))} ({r.get('n_nuevo', 0)} refs)")
    else:
        lineas.append("Colombia: sin publicaciones de este modelo")
    lineas.append(f"Costo puesto sin flete: {cop(c['total_cop'])} (TRM {op['trm']:,.0f})")
    v = op.get("venta")
    if v:
        lineas.append(f"Venta en Colombia: lista {cop(v['lista_cop'])} · objetivo {cop(v['objetivo_cop'])} · "
                      f"piso {cop(v['piso_cop'])} ({e(op['origen_co'])})")
    if op["tipo"] == "reventa":
        lineas.append(f"Flete máximo: {cop(op['flete_maximo_cop'])} · Margen al precio de retiro: "
                      f"{op['margen_en_retiro'] * 100:.0f} %")
    else:
        lineas.append(f"Descuento frente al usado de EE. UU.: {op['descuento_us'] * 100:.0f} %")
    if op.get("senales"):
        lineas.append("Señales del vendedor: " + e(", ".join(op["senales"])))
    for b in op.get("banderas") or []:
        lineas.append("⚠️ " + e(b))
    lineas.append(e(l["url"]))
    if op.get("mensaje"):
        lineas.append(f"<pre>{e(op['mensaje'])}</pre>")
    return "\n".join(lineas)


class Telegram:
    def __init__(self, token: str, chat_id: str, cliente: httpx.Client | None = None, registrar=None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id, self.cliente = chat_id, cliente or httpx.Client(timeout=20)
        self.registrar = registrar or (lambda tipo, detalle: None)

    def _enviar(self, metodo: str, datos: dict) -> bool:
        try:
            r = self.cliente.post(f"{self.base}/{metodo}", json={"chat_id": self.chat_id, **datos})
            if r.status_code != 200:
                self.registrar("telegram_error", f"{metodo}: HTTP {r.status_code}")
                return False
            return True
        except httpx.HTTPError as e:
            self.registrar("telegram_error", f"{metodo}: {type(e).__name__}")
            return False

    def alerta(self, op: dict) -> None:
        texto = formato_alerta(op)
        fotos = op["listing"].get("fotos") or []
        if fotos and len(texto) <= 1000 and self._enviar(
                "sendPhoto", {"photo": fotos[0], "caption": texto, "parse_mode": "HTML"}):
            return
        self._enviar("sendMessage", {"text": texto, "parse_mode": "HTML", "disable_web_page_preview": False})

    def aviso(self, texto: str) -> None:
        self._enviar("sendMessage", {"text": texto})


class SinAvisos:
    """Se usa cuando Telegram no está configurado: guarda los avisos en memoria."""

    def __init__(self):
        self.alertas, self.avisos = [], []

    def alerta(self, op: dict) -> None:
        self.alertas.append(op)

    def aviso(self, texto: str) -> None:
        self.avisos.append(texto)
