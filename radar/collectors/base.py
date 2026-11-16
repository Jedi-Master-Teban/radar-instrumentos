"""Navegador compartido, pausas y utilidades de lectura. Solo lectura: nunca envía formularios."""
from __future__ import annotations

import json
import random
import re
import time

PAUSA_MIN, PAUSA_MAX = 5.0, 10.0
MAX_PAGINAS = 3
MARCAS_BLOQUEO = ("captcha", "pardon our interruption", "verifica que eres humano", "unusual traffic",
                  "access denied", "checkpoint")


class LectorBloqueado(Exception):
    """El sitio pidió verificación, inicio de sesión o bloqueó la lectura. No se intenta evadir."""


_NUM = r"\d{1,3}(?:[,\.\s  ]\d{3})*(?:[\.,]\d{1,2})?|\d+(?:[\.,]\d{1,2})?"
_RANGO = re.compile(r"\d\s*(?:to|a|-|–)\s*(?:[A-Z]{2,3}\s*)?\$?\s*\d", re.I)


def _a_numero(txt: str) -> float | None:
    t = re.sub(r"[\s  ]", "", txt)
    if not t:
        return None
    # separador decimal = último punto o coma seguido de 1-2 dígitos al final
    m = re.search(r"[\.,](\d{1,2})$", t)
    if m:
        entero, dec = t[: m.start()], m.group(1)
    else:
        entero, dec = t, ""
    entero = re.sub(r"[\.,]", "", entero)
    if not entero.isdigit():
        return None
    return float(entero + ("." + dec if dec else ""))


def parse_precio(texto: str) -> tuple[float, str] | None:
    """Devuelve (monto, moneda) para 'USD' o 'COP'. None si es rango, gratis, otra moneda o ilegible."""
    if not texto:
        return None
    t = texto.strip()
    if _RANGO.search(t):
        return None
    if re.search(r"\b(EUR|GBP|JPY|CAD|AUD|MXN)\b|[€£¥]", t):
        return None
    moneda = "COP" if re.search(r"\bCOP\b", t) else "USD"
    m = re.search(_NUM, t)
    if not m or "$" not in t and moneda == "USD" and not re.search(r"\bUS\b|USD", t):
        return None
    monto = _a_numero(m.group(0))
    if monto is None or monto <= 0:
        return None
    return monto, moneda


def parse_precio_usd(texto: str, trm: float | None = None) -> float | None:
    """Precio en USD. Los precios mostrados en COP (eBay visto desde Colombia) se convierten con la TRM."""
    r = parse_precio(texto)
    if r is None:
        return None
    monto, moneda = r
    if moneda == "USD":
        return monto
    if trm:
        return round(monto / trm, 2)
    return None


def parece_bloqueo(html: str, url_final: str = "") -> bool:
    cabeza = html[:6000].lower()
    if any(m in cabeza for m in MARCAS_BLOQUEO):
        return True
    return any(s in url_final for s in ("signin.", "/login", "account-verification", "/checkpoint"))


class Navegador:
    """Context manager sobre Playwright. Un solo navegador, ritmo bajo, sin técnicas de evasión."""

    def __init__(self, perfil: str | None = None, headless: bool = True, pausa: bool = True):
        self.perfil, self.headless, self.pausa = perfil, headless, pausa
        self._pw = self._ctx = self._page = None
        self._primera = True

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        if self.perfil:
            self._ctx = self._pw.chromium.launch_persistent_context(self.perfil, headless=self.headless)
        else:
            nav = self._pw.chromium.launch(headless=self.headless)
            self._ctx = nav.new_context(locale="en-US")
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._ctx.close()
        finally:
            self._pw.stop()

    def _esperar(self):
        if self.pausa and not self._primera:
            time.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))
        self._primera = False

    def html(self, url: str) -> str:
        self._esperar()
        resp = self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self._page.wait_for_timeout(2500)
        html = self._page.content()
        if (resp is not None and resp.status in (403, 429)) or parece_bloqueo(html, self._page.url):
            raise LectorBloqueado(f"{url} → bloqueo o inicio de sesión requerido")
        return html

    def json(self, origen: str, ruta: str, cabeceras: dict | None = None):
        """Pide un JSON del mismo sitio desde la página (como lo hace el propio sitio)."""
        if not self._page.url.startswith(origen):
            self.html(origen)
        else:
            self._esperar()
        res = self._page.evaluate(
            """async ([ruta, cab]) => { const r = await fetch(ruta, {headers: cab});
                 return {status: r.status, texto: r.ok ? await r.text() : ''}; }""",
            [ruta, cabeceras or {"Accept": "application/json"}],
        )
        if res["status"] in (401, 403, 429):
            raise LectorBloqueado(f"{origen}{ruta} → HTTP {res['status']}")
        if res["status"] != 200:
            return None
        try:
            return json.loads(res["texto"])
        except ValueError:
            return None
