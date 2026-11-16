"""Tiendas establecidas: lectores genéricos por plataforma (Shopify, WooCommerce) y Guitar Center."""
from __future__ import annotations

import json
import re
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup

from ..models import PrecioTienda
from .base import Navegador

# Tiendas de Colombia verificadas el 15 nov 2026. Se pueden añadir más desde el tablero.
TIENDAS_CO_DEFECTO = [
    {"nombre": "Ortizo", "origen": "https://ortizo.com.co", "plataforma": "shopify"},
    {"nombre": "La Colonial", "origen": "https://www.lacolonial.com.co", "plataforma": "shopify"},
    {"nombre": "TMS Music", "origen": "https://tmsmusic.co", "plataforma": "shopify"},
    {"nombre": "Music Head Store", "origen": "https://musicheadstore.com", "plataforma": "woocommerce"},
    {"nombre": "Duosonic", "origen": "https://duosonic.co", "plataforma": "woocommerce"},
]


def parse_shopify(datos: dict | None, tienda: dict) -> list[PrecioTienda]:
    productos = (((datos or {}).get("resources") or {}).get("results") or {}).get("products") or []
    salida = []
    for p in productos:
        try:
            precio = float(p["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if precio <= 0 or p.get("available") is False:
            continue
        salida.append(PrecioTienda(tienda["nombre"], p.get("title", "").strip(), precio, "nuevo",
                                   tienda["origen"] + (p.get("url") or "").split("?")[0]))
    return salida


def parse_woocommerce(datos: list | None, tienda: dict) -> list[PrecioTienda]:
    salida = []
    for p in datos or []:
        try:
            pr = p["prices"]
            if pr.get("currency_code") not in (None, "COP"):
                continue
            precio = float(pr["price"]) / (10 ** int(pr.get("currency_minor_unit", 0)))
        except (KeyError, TypeError, ValueError):
            continue
        if precio <= 0 or p.get("is_in_stock") is False:
            continue
        salida.append(PrecioTienda(tienda["nombre"], BeautifulSoup(p.get("name", ""), "html.parser").get_text().strip(),
                                   precio, "nuevo", p.get("permalink", "")))
    return salida


def buscar_tienda_co(nav: Navegador, tienda: dict, consulta: str) -> list[PrecioTienda]:
    if tienda["plataforma"] == "shopify":
        ruta = f"/search/suggest.json?q={quote(consulta)}&resources[type]=product&resources[limit]=10"
        return parse_shopify(nav.json(tienda["origen"], ruta), tienda)
    if tienda["plataforma"] == "woocommerce":
        ruta = f"/wp-json/wc/store/v1/products?search={quote(consulta)}&per_page=10"
        return parse_woocommerce(nav.json(tienda["origen"], ruta), tienda)
    raise ValueError(f"plataforma no soportada: {tienda['plataforma']}")


# ---------- Guitar Center (EE. UU.) ----------

def url_guitar_center(consulta: str, condicion: str) -> str:
    cond = "Used" if condicion == "usado" else "New"
    return f"https://www.guitarcenter.com/search?Ntt={quote_plus(consulta)}&filters=condition:{cond}"


def parse_guitar_center(html: str, condicion: str) -> list[PrecioTienda]:
    sopa = BeautifulSoup(html, "html.parser")
    salida = []
    for s in sopa.select('script[type="application/ld+json"]'):
        try:
            j = json.loads(s.string or "")
        except ValueError:
            continue
        if not isinstance(j, dict) or j.get("@type") != "CollectionPage":
            continue
        for el in (j.get("mainEntity") or {}).get("itemListElement") or []:
            item = el.get("item") or {}
            oferta = item.get("offers") or {}
            try:
                precio = float(oferta["price"])
            except (KeyError, TypeError, ValueError):
                continue
            nombre = item.get("name", "").strip()
            es_usado = bool(re.match(r"used\b", nombre, re.I))
            if oferta.get("priceCurrency") != "USD" or precio <= 0 or es_usado != (condicion == "usado"):
                continue
            salida.append(PrecioTienda("Guitar Center", nombre, precio, condicion, item.get("url", "")))
    return salida


def buscar_guitar_center(nav: Navegador, consulta: str, condicion: str) -> list[PrecioTienda]:
    return parse_guitar_center(nav.html(url_guitar_center(consulta, condicion)), condicion)
