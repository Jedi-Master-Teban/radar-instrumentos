"""Facebook Marketplace con la sesión que el usuario inició a mano. Solo lectura.

SIN CALIBRAR con una página real (requiere la sesión del usuario): el lector recorre los JSON
embebidos en la página buscando publicaciones, sin depender de clases CSS.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Listing, PrecioTienda
from .base import LectorBloqueado, Navegador

_LOGIN = re.compile(r'id="login_form"|name="login"|/login/\?next|"is_logged_out":true', re.I)


def url_us(consulta: str, ciudad: str) -> str:
    return (f"https://www.facebook.com/marketplace/{ciudad}/search"
            f"?query={quote(consulta)}&deliveryMethod=shipping&itemCondition=used_like_new%2Cused_good")


def url_co(consulta: str, ciudad: str = "bogota") -> str:
    return f"https://www.facebook.com/marketplace/{ciudad}/search?query={quote(consulta)}"


def _recorrer(nodo):
    if isinstance(nodo, dict):
        if "marketplace_listing_title" in nodo and "listing_price" in nodo:
            yield nodo
        for v in nodo.values():
            yield from _recorrer(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _recorrer(v)


def _nodos(html: str) -> list[dict]:
    if _LOGIN.search(html[:200000]) and "marketplace_listing_title" not in html:
        raise LectorBloqueado("facebook: sesión requerida")
    sopa = BeautifulSoup(html, "html.parser")
    vistos, salida = set(), []
    for s in sopa.select('script[type="application/json"]'):
        texto = s.string or ""
        if "marketplace_listing_title" not in texto:
            continue
        try:
            datos = json.loads(texto)
        except ValueError:
            continue
        for n in _recorrer(datos):
            if n.get("id") and n["id"] not in vistos:
                vistos.add(n["id"])
                salida.append(n)
    return salida


def _precio(n: dict) -> tuple[float, str] | None:
    lp = n.get("listing_price") or {}
    try:
        monto = float(lp.get("amount"))
    except (TypeError, ValueError):
        return None
    if monto <= 0:
        return None
    return monto, (lp.get("currency") or "USD")


def parse_busqueda(html: str) -> list[Listing]:
    """Publicaciones de EE. UU. en USD que se pueden enviar."""
    salida = []
    for n in _nodos(html):
        pr = _precio(n)
        entrega = [str(d).upper() for d in (n.get("delivery_types") or [])]
        if pr is None or pr[1] != "USD" or n.get("is_sold") or n.get("is_pending"):
            continue
        if not any("SHIPPING" in d for d in entrega):
            continue
        foto = (((n.get("primary_listing_photo") or {}).get("image")) or {}).get("uri")
        salida.append(Listing(
            plataforma="facebook", id_externo=str(n["id"]),
            url=f"https://www.facebook.com/marketplace/item/{n['id']}/",
            titulo=n["marketplace_listing_title"].strip(), precio_usd=pr[0], envio_us_usd=0.0,
            acepta_ofertas=True, hace_envios=True, fotos=[foto] if foto else [],
        ))
    return salida


def parse_busqueda_co(html: str) -> list[PrecioTienda]:
    salida = []
    for n in _nodos(html):
        pr = _precio(n)
        if pr is None or pr[1] != "COP" or n.get("is_sold"):
            continue
        salida.append(PrecioTienda("Facebook Marketplace CO", n["marketplace_listing_title"].strip(), pr[0],
                                   "usado", f"https://www.facebook.com/marketplace/item/{n['id']}/"))
    return salida


def buscar_us(nav: Navegador, consulta: str, ciudad: str) -> list[Listing]:
    return parse_busqueda(nav.html(url_us(consulta, ciudad)))


def buscar_co(nav: Navegador, consulta: str) -> list[PrecioTienda]:
    return parse_busqueda_co(nav.html(url_co(consulta)))
