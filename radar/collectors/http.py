"""Cliente HTTP sencillo (sin navegador) para sitios que publican JSON abierto, como las tiendas de Colombia."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from .base import LectorBloqueado

AGENTE = "radar-instrumentos/0.1 (uso personal)"


class ClienteHttp:
    def __init__(self, cliente: httpx.Client | None = None, pausa: float = 2.0):
        self.cliente = cliente or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": AGENTE})
        self.pausa, self._ultimo = pausa, {}

    def json(self, origen: str, ruta: str, cabeceras: dict | None = None):
        host = urlparse(origen).hostname or ""
        falta = self._ultimo.get(host, 0) + self.pausa - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        self._ultimo[host] = time.monotonic()
        try:
            r = self.cliente.get(origen + ruta, headers=cabeceras or {"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise LectorBloqueado(f"{origen}: {type(e).__name__}") from e
        if r.status_code in (401, 403, 429):
            raise LectorBloqueado(f"{origen}{ruta[:60]} → HTTP {r.status_code}")
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None
