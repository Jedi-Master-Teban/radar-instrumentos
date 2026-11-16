"""MercadoLibre Colombia. Exige sesión iniciada (se comprobó el 15 nov 2026): usa el perfil dedicado.

SIN CALIBRAR con una página real: los selectores siguen la estructura conocida de las tarjetas 'poly-card'.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import PrecioTienda
from .base import Navegador, _a_numero


def url_busqueda(consulta: str) -> str:
    return "https://listado.mercadolibre.com.co/" + quote(re.sub(r"\s+", "-", consulta.strip().lower()))


def parse_busqueda(html: str) -> list[PrecioTienda]:
    sopa = BeautifulSoup(html, "html.parser")
    salida = []
    for c in sopa.select(".poly-card") or sopa.select("li.ui-search-layout__item"):
        t = c.select_one(".poly-component__title, .ui-search-item__title")
        precio_el = c.select_one(".poly-price__current .andes-money-amount__fraction, .andes-money-amount__fraction")
        if not (t and precio_el):
            continue
        precio = _a_numero(precio_el.get_text(strip=True))
        if not precio:
            continue
        texto = c.get_text(" ", strip=True).lower()
        a = t if t.name == "a" else t.find_parent("a") or c.select_one("a[href]")
        salida.append(PrecioTienda("MercadoLibre", t.get_text(" ", strip=True), precio,
                                   "usado" if re.search(r"\busado\b", texto) else "nuevo",
                                   (a.get("href") or "").split("#")[0] if a else ""))
    return salida


def buscar(nav: Navegador, consulta: str) -> list[PrecioTienda]:
    return parse_busqueda(nav.html(url_busqueda(consulta)))
